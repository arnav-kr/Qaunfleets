"""Frozen confirmed-commitment depot fixtures, classical reference and independent checks."""

import copy
import csv
import hashlib
import itertools
import json
import math
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import numpy as np

from scheduler import EXAMPLE, solve

ROOT = Path(__file__).resolve().parent
SCENARIOS = ROOT / "data/scenarios/depot-v1"
OUT = ROOT / "artifacts/depot-reference"
TOL = 1e-5


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def fixtures():
    base = {
        "schema_version": "depot-v1",
        "scenario_id": "normal_flat",
        "start": "2026-10-29T18:00:00+05:30",
        "timezone": "Asia/Calcutta",
        "slot_minutes": 30,
        "capacity_kw": 25.6,
        "historic_peak_kw": 18.0,
        "demand_rate": 8.0,
        "efficiency": 0.9,
        "risk_weight": 0.0,
        "prediction_mode": "confirmed_only",
        "backend": "highs",
        "tariffs": [0.20] * 28,
        "base_load_kw": [10.0] * 8 + [4.0] * 16 + [8.0] * 4,
        "chargers": [{"id": f"C{i}", "kw": 7.2} for i in [1, 2, 3]],
        "vehicles": [
            {
                "id": f"V{i + 1}",
                "arrival": a,
                "deadline": d,
                "kwh": e,
                "max_kw": 7.2,
                "compatible": c,
            }
            for i, (a, d, e, c) in enumerate(
                [
                    (0, 22, 12.96, ["C1", "C2"]),
                    (1, 24, 19.44, ["C2", "C3"]),
                    (2, 26, 12.96, ["C1", "C3"]),
                    (4, 28, 9.72, ["C1", "C2", "C3"]),
                    (6, 24, 16.2, ["C1", "C2", "C3"]),
                    (8, 28, 9.72, ["C1", "C2", "C3"]),
                ]
            )
        ],
        "assumptions": {
            "provenance": "All operational values are constructed engineering assumptions, not measured NREL/Optimise Prime fleet records.",
            "operation": "Small overnight delivery-van depot; required energy is dispatcher-supplied battery top-up, not target SOC.",
            "currency": "USD demo units; synthetic rates, not a quoted utility tariff",
            "billing": "Single overnight horizon inside October 2026 billing period. Historical peak is already established before this horizon. Only incremental EV bill is claimed; previous period energy consumption is not supplied.",
            "charging": "Fixed AC power with a reduced final slot; one contiguous visit on one compatible charger; constant efficiency; no taper/V2G/storage.",
            "movement": "Vehicles may wait unplugged; staff can connect/disconnect at slot boundaries. Travel/setup time is idealized to zero and staff concurrency is not modelled.",
            "availability": "All listed chargers available for the whole horizon. Disruption fixtures are separate pre-start revisions, not mid-session recovery.",
            "prediction": "Disabled. All listed deadlines and energy requirements are confirmed. No unplug forecast is substituted for a commitment.",
        },
    }
    tou = copy.deepcopy(base)
    tou.update(
        scenario_id="tariff_and_peak", tariffs=[0.32] * 8 + [0.18] * 4 + [0.10] * 8 + [0.22] * 8
    )
    disruption = copy.deepcopy(tou)
    disruption.update(
        scenario_id="prestart_outage_derating",
        capacity_kw=17.2,
        chargers=[c for c in disruption["chargers"] if c["id"] != "C3"],
    )
    for v in disruption["vehicles"]:
        v["compatible"] = [c for c in v["compatible"] if c != "C3"]
    disruption["assumptions"]["disruption"] = (
        "Before 18:00, C3 is unavailable and site capacity falls to 17.2 kW; no delivery has occurred."
    )
    impossible = copy.deepcopy(tou)
    impossible["scenario_id"] = "impossible_departure"
    impossible["vehicles"][0]["deadline"] = 1
    impossible["assumptions"]["disruption"] = (
        "V1 now requires 12.96 battery kWh within 30 minutes; its maximum possible delivery is 3.24 kWh."
    )
    return [base, tou, disruption, impossible]


def freeze():
    SCENARIOS.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for data in fixtures():
        path = SCENARIOS / (data["scenario_id"] + ".json")
        if path.exists():
            if digest(json.loads(path.read_text())) != digest(data):
                raise ValueError(
                    "Frozen v1 scenario changed; create an explicit new version instead of overwriting"
                )
        else:
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        manifest[path.name] = digest(data)
    (SCENARIOS / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return [json.loads((SCENARIOS / (d["scenario_id"] + ".json")).read_text()) for d in fixtures()]


def menu(data):
    """Independently enumerate the fixed profile universe for export/comparison."""
    n = len(data["tariffs"])
    dt = data["slot_minutes"] / 60
    profiles = []
    for v in data["vehicles"]:
        for c in data["chargers"]:
            if c["id"] not in v["compatible"]:
                continue
            power = min(c["kw"], v["max_kw"])
            length = math.ceil(v["kwh"] / data["efficiency"] / power / dt - 1e-10)
            for start in range(v["arrival"], v["deadline"] - length + 1):
                load = [0.0] * n
                left = v["kwh"] / data["efficiency"]
                for t in range(start, start + length):
                    load[t] = min(power, left / dt)
                    left -= load[t] * dt
                if any(
                    p + b > data["capacity_kw"] + 1e-8 for p, b in zip(load, data["base_load_kw"])
                ):
                    continue
                profiles.append(
                    {
                        "profile_id": f"{v['id']}:{c['id']}:{start}",
                        "vehicle": v["id"],
                        "charger": c["id"],
                        "start_slot": start,
                        "end_slot": start + length,
                        "grid_kw_by_slot": load,
                        "battery_kwh": v["kwh"],
                        "grid_kwh": sum(load) * dt,
                        "energy_cost": sum(p * t * dt for p, t in zip(load, data["tariffs"])),
                    }
                )
    return profiles


def ledger(data, ev):
    dt = data["slot_minutes"] / 60
    site = [a + b for a, b in zip(ev, data["base_load_kw"])]
    ev_energy = sum(p * t * dt for p, t in zip(ev, data["tariffs"]))
    base_energy = sum(p * t * dt for p, t in zip(data["base_load_kw"], data["tariffs"]))
    base_peak = max(data["historic_peak_kw"], max(data["base_load_kw"]))
    new_peak = max(data["historic_peak_kw"], max(site))
    increment = (new_peak - base_peak) * data["demand_rate"]
    return {
        "energy_cost": ev_energy,
        "incremental_demand_charge": increment,
        "incremental_bill": ev_energy + increment,
        "peak_kw": max(site),
        "base_horizon_energy_cost": base_energy,
        "site_horizon_energy_cost": base_energy + ev_energy,
        "baseline_period_peak_charge": base_peak * data["demand_rate"],
        "with_ev_period_peak_charge": new_peak * data["demand_rate"],
        "aggregate_ev_kw": list(ev),
        "aggregate_site_kw": site,
    }


def greedy(data):
    """Offline earliest-deadline, earliest-available contiguous visit. No backtracking."""
    n = len(data["tariffs"])
    profiles = menu(data)
    occupied = {c["id"]: [False] * n for c in data["chargers"]}
    load = np.zeros(n)
    chosen = []
    for v in sorted(data["vehicles"], key=lambda v: (v["deadline"], v["arrival"], v["id"])):
        for p in sorted(
            [p for p in profiles if p["vehicle"] == v["id"]],
            key=lambda p: (p["start_slot"], p["charger"]),
        ):
            a, b = p["start_slot"], p["end_slot"]
            candidate = load + np.array(p["grid_kw_by_slot"])
            if any(occupied[p["charger"]][a:b]) or np.any(
                candidate + data["base_load_kw"] > data["capacity_kw"] + 1e-8
            ):
                continue
            chosen.append(p)
            load = candidate
            occupied[p["charger"]][a:b] = [True] * (b - a)
            break
        else:
            return {
                "status": "no_valid_solution_found",
                "schedule": [],
                "reason": "Greedy could not place every vehicle; not a proof of infeasibility.",
                "scenario_sha256": digest(data),
            }
    origin = datetime.fromisoformat(data["start"])
    dt = data["slot_minutes"]
    for p in chosen:
        p["start"] = (origin + timedelta(minutes=dt * p["start_slot"])).isoformat()
        p["end"] = (origin + timedelta(minutes=dt * p["end_slot"])).isoformat()
    return {
        "status": "feasible",
        "solver": "earliest-deadline earliest-fit heuristic",
        "scenario_sha256": digest(data),
        "schedule": chosen,
        **ledger(data, load),
    }


def validate(data, result):
    """Recompute from exported per-vehicle power, never trust solver validation flags."""
    errors = []
    n = len(data["tariffs"])
    dt = data["slot_minutes"] / 60
    origin = datetime.fromisoformat(data["start"])
    vehicles = {v["id"]: v for v in data["vehicles"]}
    chargers = {c["id"]: c for c in data["chargers"]}
    occupancy = {c: np.zeros(n) for c in chargers}
    ev = np.zeros(n)
    seen = set()
    ready = 0
    if result.get("scenario_sha256") != digest(data):
        errors.append("scenario hash mismatch / stale plan")
    for p in result.get("schedule", []):
        vid = p.get("vehicle")
        cid = p.get("charger")
        if vid not in vehicles or cid not in chargers:
            errors.append("unknown vehicle or charger")
            continue
        v = vehicles[vid]
        c = chargers[cid]
        if vid in seen:
            errors.append("duplicate vehicle assignment")
        seen.add(vid)
        a, b = p.get("start_slot"), p.get("end_slot")
        if not isinstance(a, int) or not isinstance(b, int) or not 0 <= a < b <= n:
            errors.append("invalid slot interval")
            continue
        if not v["arrival"] <= a < b <= v["deadline"]:
            errors.append(f"{vid}: arrival/deadline violation")
        if cid not in v["compatible"]:
            errors.append(f"{vid}: incompatible charger")
        load = np.array(p.get("grid_kw_by_slot", []), dtype=float)
        if load.shape != (n,) or not np.isfinite(load).all():
            errors.append("invalid power vector")
            continue
        if np.any(load < -TOL) or np.any(load > min(v["max_kw"], c["kw"]) + TOL):
            errors.append(f"{vid}: power/rate violation")
        if np.any(abs(load[:a]) > TOL) or np.any(abs(load[b:]) > TOL):
            errors.append("power outside visit")
        if np.any(load[a:b] <= 0):
            errors.append("non-contiguous visit")
        # Enforce the declared finite-profile contract, not just general physical feasibility.
        power = min(v["max_kw"], c["kw"])
        length = math.ceil(v["kwh"] / data["efficiency"] / power / dt - 1e-10)
        if b - a != length or (b - a > 1 and np.any(abs(load[a : b - 1] - power) > TOL)):
            errors.append("outside frozen profile formulation")
        energy = float(load.sum() * dt * data["efficiency"])
        if abs(energy - v["kwh"]) > TOL:
            errors.append(f"{vid}: required energy mismatch")
        reported_energy = [float(p.get("battery_kwh", -1)), float(p.get("grid_kwh", -1))]
        if (
            not all(math.isfinite(x) for x in reported_energy)
            or abs(reported_energy[0] - energy) > TOL
            or abs(reported_energy[1] - load.sum() * dt) > TOL
        ):
            errors.append("reported energy mismatch")
        if energy >= v["kwh"] - TOL and a >= v["arrival"] and b <= v["deadline"]:
            ready += 1
        if (
            p.get("start") != (origin + timedelta(hours=a * dt)).isoformat()
            or p.get("end") != (origin + timedelta(hours=b * dt)).isoformat()
        ):
            errors.append("timestamp/slot mismatch")
        occupancy[cid][a:b] += 1
        ev += load
    if seen != set(vehicles):
        errors.append("missing mandatory vehicle")
    if any(np.any(x > 1) for x in occupancy.values()):
        errors.append("charger overlap")
    site = ev + data["base_load_kw"]
    violations = int(sum(site > data["capacity_kw"] + TOL))
    if violations:
        errors.append("site capacity exceeded")
    recomputed = ledger(data, ev)
    for key in ["energy_cost", "incremental_demand_charge", "incremental_bill", "peak_kw"]:
        if (
            key not in result
            or not math.isfinite(float(result[key]))
            or abs(result[key] - recomputed[key]) > TOL
        ):
            errors.append(f"{key}: incorrect reported metric")
    for key in ["aggregate_ev_kw", "aggregate_site_kw"]:
        reported = np.array(result.get(key, []), dtype=float)
        if (
            reported.shape != (n,)
            or not np.isfinite(reported).all()
            or not np.allclose(reported, recomputed[key], atol=TOL, rtol=0)
        ):
            errors.append(f"{key}: incorrect reported loading")
    return {
        "passed": not errors,
        "errors": errors,
        "confirmed_ready": ready,
        "mandatory_vehicles": len(vehicles),
        "capacity_violations": violations,
        "recomputed": recomputed,
    }


def reference(data):
    # Fail loudly if the confirmed-only reference accidentally loads an ML artifact.
    with patch(
        "scheduler.joblib.load",
        side_effect=AssertionError("Classical commitment reference must not load ML"),
    ):
        r = solve(data)
    r["scenario_sha256"] = digest(data)
    return r


def tests(results):
    checks = []

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        checks.append(name)

    for data, r, g in results:
        if data["scenario_id"] == "impossible_departure":
            check(
                "impossible request rejected without accepted schedule",
                r["status"] == "infeasible" and not r["schedule"],
            )
            v = data["vehicles"][0]
            bound = (
                (v["deadline"] - v["arrival"])
                * data["slot_minutes"]
                / 60
                * v["max_kw"]
                * data["efficiency"]
            )
            check("impossible case has independent physical certificate", bound < v["kwh"])
            continue
        check(
            data["scenario_id"] + ": exact optimum certified",
            r["status"] == "optimal" and r["mip_gap"] <= 1e-7,
        )
        check(data["scenario_id"] + ": independent validation", validate(data, r)["passed"])
        check(
            data["scenario_id"] + ": heuristic feasible",
            g["status"] == "feasible" and validate(data, g)["passed"],
        )
        check(
            data["scenario_id"] + ": optimizer no worse at identical service",
            r["incremental_bill"] <= g["incremental_bill"] + TOL,
        )
        check(
            data["scenario_id"] + ": no fabricated prediction",
            all(
                f["predicted_disconnect"] is None and f["source"] == "confirmed_only"
                for f in r["forecasts"]
            ),
        )
        check(
            data["scenario_id"] + ": exported profile count matches solver",
            len(menu(data)) == r["profiles"],
        )
    d, r, g = results[1]
    check(
        "tariff fixture has nontrivial improvement",
        g["incremental_bill"] - r["incremental_bill"] > 0.01,
    )
    mutations = {}
    x = copy.deepcopy(r)
    x["schedule"][0]["grid_kw_by_slot"] = [0.0] * len(d["tariffs"])
    mutations["missing energy"] = x
    x = copy.deepcopy(r)
    x["schedule"].append(copy.deepcopy(x["schedule"][0]))
    mutations["duplicate/overlapping visit"] = x
    x = copy.deepcopy(r)
    x["schedule"][0]["charger"] = "unknown"
    mutations["unknown charger"] = x
    x = copy.deepcopy(r)
    x["schedule"][0]["end_slot"] = 29
    mutations["invalid deadline/slots"] = x
    x = copy.deepcopy(r)
    x["schedule"][0]["grid_kw_by_slot"][x["schedule"][0]["start_slot"]] = 100
    mutations["overload"] = x
    x = copy.deepcopy(r)
    x["incremental_bill"] -= 1
    mutations["wrong bill"] = x
    x = copy.deepcopy(r)
    x["scenario_sha256"] = "old"
    mutations["stale plan"] = x
    x = copy.deepcopy(r)
    x["schedule"] = x["schedule"][1:]
    mutations["missing commitment"] = x
    x = copy.deepcopy(r)
    x["schedule"][0]["battery_kwh"] = float("nan")
    mutations["nonfinite reported energy"] = x
    for name, x in mutations.items():
        check("validator rejects " + name, not validate(d, x)["passed"])
    derated = copy.deepcopy(d)
    derated["capacity_kw"] = 17.2
    x = copy.deepcopy(r)
    x["scenario_sha256"] = digest(derated)
    check(
        "independent site-capacity check catches otherwise physical plan",
        "site capacity exceeded" in validate(derated, x)["errors"],
    )
    x = copy.deepcopy(r)
    next(p for p in x["schedule"] if p["vehicle"] == "V1")["charger"] = "C3"
    check(
        "known but incompatible charger rejected",
        "V1: incompatible charger" in validate(d, x)["errors"],
    )
    tiny = copy.deepcopy(d)
    tiny.update(
        scenario_id="hand_calculated",
        tariffs=[0.1, 0.2],
        base_load_kw=[0.0, 0.0],
        capacity_kw=14.4,
        historic_peak_kw=7.2,
        demand_rate=10.0,
    )
    tiny["chargers"] = [{"id": "A", "kw": 7.2}, {"id": "B", "kw": 7.2}]
    tiny["vehicles"] = [
        {"id": v, "arrival": 0, "deadline": 2, "kwh": 3.24, "max_kw": 7.2, "compatible": ["A", "B"]}
        for v in ["X", "Y"]
    ]
    peak = reference(tiny)
    check(
        "hand-calculated peak-aware optimum",
        abs(peak["incremental_bill"] - 1.08) < TOL and abs(peak["peak_kw"] - 7.2) < TOL,
    )
    # Enumerate every menu pair in this tiny case independently of the MILP.
    options = menu(tiny)
    bills = []
    for a, b in itertools.product(
        [p for p in options if p["vehicle"] == "X"], [p for p in options if p["vehicle"] == "Y"]
    ):
        if a["charger"] == b["charger"] and a["start_slot"] == b["start_slot"]:
            continue
        bills.append(
            ledger(tiny, np.array(a["grid_kw_by_slot"]) + b["grid_kw_by_slot"])["incremental_bill"]
        )
    check("exhaustive tiny menu agrees", abs(min(bills) - peak["incremental_bill"]) < TOL)
    tiny["demand_rate"] = 0.0
    energy = reference(tiny)
    check(
        "energy-only optimum concentrates in cheapest slot",
        abs(energy["incremental_bill"] - 0.72) < TOL and abs(energy["peak_kw"] - 14.4) < TOL,
    )
    tiny["demand_rate"] = 10.0
    tiny["historic_peak_kw"] = 30.0
    historic = reference(tiny)
    check(
        "existing billing peak not charged twice",
        abs(historic["incremental_demand_charge"]) < TOL
        and abs(historic["incremental_bill"] - 0.72) < TOL,
    )
    legacy = copy.deepcopy(EXAMPLE)
    legacy["backend"] = "highs"
    old = solve(legacy)
    check(
        "existing model-enabled scheduler still works",
        old["validated"]
        and old["confirmed_compliance"] == 1
        and all(f["predicted_disconnect"] is not None for f in old["forecasts"]),
    )
    invalid = copy.deepcopy(d)
    invalid["risk_weight"] = 1
    try:
        reference(invalid)
    except ValueError:
        checks.append("confirmed-only mode rejects forecast-risk objective")
    else:
        raise AssertionError("Forecast risk accepted in confirmed-only mode")
    return checks


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    for data in freeze():
        r = reference(data)
        g = greedy(data)
        profiles = menu(data)
        results.append((data, r, g))
        bundle = {
            "scenario": data,
            "scenario_sha256": digest(data),
            "reference": r,
            "heuristic": g,
            "reference_validation": validate(data, r) if r["schedule"] else None,
            "heuristic_validation": validate(data, g) if g["schedule"] else None,
        }
        (OUT / (data["scenario_id"] + ".json")).write_text(json.dumps(bundle, indent=2))
        (OUT / (data["scenario_id"] + "_profiles.json")).write_text(
            json.dumps(
                {
                    "scenario_sha256": digest(data),
                    "profile_count": len(profiles),
                    "profiles": profiles,
                },
                indent=2,
            )
        )
        if r["schedule"]:
            with (OUT / (data["scenario_id"] + "_schedule.csv")).open("w", newline="") as f:
                keys = ["vehicle", "charger", "start", "end", "battery_kwh", "grid_kwh"]
                w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
                w.writeheader()
                w.writerows(r["schedule"])
            with (OUT / (data["scenario_id"] + "_loading.csv")).open("w", newline="") as f:
                w = csv.writer(f)
                w.writerow(
                    [
                        "slot",
                        "start",
                        "base_kw",
                        "ev_kw",
                        "site_kw",
                        "capacity_kw",
                        "tariff_per_kwh",
                    ]
                )
                origin = datetime.fromisoformat(data["start"])
                for t in range(len(data["tariffs"])):
                    w.writerow(
                        [
                            t,
                            (origin + timedelta(minutes=data["slot_minutes"] * t)).isoformat(),
                            data["base_load_kw"][t],
                            r["aggregate_ev_kw"][t],
                            r["aggregate_site_kw"][t],
                            data["capacity_kw"],
                            data["tariffs"][t],
                        ]
                    )
        print(
            data["scenario_id"],
            r["status"],
            r.get("incremental_bill"),
            g.get("incremental_bill"),
            flush=True,
        )
    checks = tests(results)
    report = {
        "passed": True,
        "checks": checks,
        "scenario_hashes": {d["scenario_id"]: digest(d) for d, r, g in results},
        "source_hashes": {
            p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
            for p in ["scheduler.py", "depot_reference.py"]
        },
    }
    (OUT / "acceptance.json").write_text(json.dumps(report, indent=2))
    print("Acceptance checks passed:", len(checks))


if __name__ == "__main__":
    main()
