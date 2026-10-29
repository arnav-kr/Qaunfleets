from copy import deepcopy

import pytest

from execution_replay import replan
from product_pipeline import run


def fixture():
    scenario = {
        "start": "2026-10-29T18:00:00+05:30",
        "slot_minutes": 30,
        "capacity_kw": 10,
        "historic_peak_kw": 0,
        "demand_rate": 2,
        "efficiency": 1,
        "tariffs": [0.1] * 8,
        "base_load_kw": [1] * 8,
        "backend": "highs",
        "forecast_source": "none",
        "chargers": [{"id": "C1", "kw": 4}, {"id": "C2", "kw": 4}],
        "vehicles": [
            {"id": "V1", "arrival": 0, "deadline": 6, "kwh": 8, "max_kw": 4},
            {"id": "V2", "arrival": 0, "deadline": 8, "kwh": 8, "max_kw": 4},
        ],
    }
    return scenario, run(scenario)


def apply(scenario, result, event, slot=1):
    return replan({"scenario": scenario, "result": result, "event": event, "slot": slot})


def assert_history(previous, updated, now):
    for old in previous["schedule"]:
        new = next(r for r in updated["schedule"] if r["vehicle"] == old["vehicle"])
        assert new["grid_kw_by_slot"][:now] == old["grid_kw_by_slot"][:now]


def test_actual_early_departure_records_shortfall_without_rewriting_history():
    s, r = fixture()
    out = apply(s, r, {"type": "depart_now", "vehicle": "V1"})
    assert_history(r, out["result"], 1)
    service = next(v for v in out["result"]["replay"]["service"] if v["vehicle"] == "V1")
    assert service["realized_shortfall_kwh"] >= 6
    assert not out["result"]["validated"]
    assert all(p == 0 for p in out["result"]["schedule"][0]["grid_kw_by_slot"][1:])


def test_occupied_charger_blocks_power_but_preserves_previous_delivery():
    s, r = fixture()
    out = apply(s, r, {"type": "occupied", "charger": "C1", "until": 4})
    assert_history(r, out["result"], 1)
    for row in out["result"]["schedule"]:
        assert all(row["charger_by_slot"][t] != "C1" for t in range(1, 4))
    assert out["result"]["validation_report"]["passed"]


def test_release_shortens_only_the_future_bay_hold():
    s, r = fixture()
    held = apply(s, r, {"type": "occupied", "charger": "C1", "until": 5}, 1)
    released = apply(held["scenario"], held["result"], {"type": "release", "charger": "C1"}, 2)
    assert released["scenario"]["charger_blocks"] == [{"charger": "C1", "start": 1, "end": 2}]
    assert_history(held["result"], released["result"], 2)
    assert released["result"]["validation_report"]["passed"]


def test_solver_failure_records_observed_departure_and_holds_future(monkeypatch):
    s, r = fixture()

    def fail(*args, **kwargs):
        raise RuntimeError("solver unavailable")

    monkeypatch.setattr("execution_replay.solve", fail)
    out = apply(s, r, {"type": "depart_now", "vehicle": "V1"}, 1)
    assert out["scenario"]["vehicles"][0]["actual_departure"] == 1
    assert out["result"]["status"] == "safe_hold"
    assert out["result"]["replay"]["future_solver_status"] == "solver_error"
    assert_history(r, out["result"], 1)
    assert all(power == 0 for power in out["result"]["aggregate_ev_kw"][1:])


def test_load_change_preserves_energy_cost_and_rechecks_capacity():
    s, r = fixture()
    out = apply(s, r, {"type": "load", "delta_kw": 3, "until": 3})
    assert_history(r, out["result"], 1)
    assert out["scenario"]["base_load_kw"][0] == 1
    assert out["result"]["replay"]["realized_energy_cost"] == pytest.approx(
        r["aggregate_ev_kw"][0] * 0.5 * 0.1
    )
    assert out["result"]["capacity_violations"] == 0


def test_background_overload_is_reported_and_future_charging_stops():
    s, r = fixture()
    out = apply(s, r, {"type": "load", "delta_kw": 12, "until": 3})
    assert out["result"]["status"] == "safe_hold"
    assert out["result"]["capacity_violations"] == 2
    assert not out["result"]["independent_validation"]
    assert all(p == 0 for p in out["result"]["aggregate_ev_kw"][1:])


def test_sequential_events_keep_departure_and_do_not_rewrite_history():
    s, r = fixture()
    first = apply(s, r, {"type": "depart_now", "vehicle": "V1"})
    second = apply(
        first["scenario"], first["result"], {"type": "load", "delta_kw": 1, "until": 4}, 2
    )
    assert_history(first["result"], second["result"], 2)
    assert second["scenario"]["vehicles"][0]["actual_departure"] == 1
    with pytest.raises(ValueError, match="cannot precede"):
        apply(second["scenario"], second["result"], {"type": "load", "delta_kw": 1, "until": 4}, 1)


def test_new_deadline_keeps_confirmed_requirement_and_remaining_energy():
    s, r = fixture()
    out = apply(s, r, {"type": "deadline", "vehicle": "V1", "deadline": 5})
    assert_history(r, out["result"], 1)
    for row in out["result"]["schedule"]:
        assert row["battery_kwh"] <= 8 + 1e-5


def test_original_inputs_are_not_mutated():
    s, r = fixture()
    before = deepcopy((s, r))
    apply(s, r, {"type": "occupied", "charger": "C1", "until": 3})
    assert (s, r) == before


def test_fixed_rate_and_final_partial_slot_are_preserved():
    scenario, _ = fixture()
    scenario["vehicles"][0]["kwh"] = 7
    previous = run(scenario)
    updated = apply(scenario, previous, {"type": "occupied", "charger": "C1", "until": 3})["result"]
    assert_history(previous, updated, 1)
    for row in updated["schedule"]:
        for segment in row["segments"]:
            powers = [p for p in segment["grid_kw_by_slot"] if p > 1e-5]
            assert all(p == pytest.approx(4) for p in powers[:-1])
            assert powers[-1] <= 4
        assert row["battery_kwh"] == pytest.approx(
            next(v["kwh"] for v in scenario["vehicles"] if v["id"] == row["vehicle"])
        )
