import json
from pathlib import Path

from depot_reference import greedy
from product_pipeline import run


def main():
    d = {
        "scenario_id": "quantum_circuit_demo",
        "start": "2026-10-29T18:00:00+05:30",
        "slot_minutes": 30,
        "capacity_kw": 1,
        "historic_peak_kw": 1,
        "demand_rate": 8,
        "efficiency": 1,
        "risk_weight": 0,
        "prediction_mode": "confirmed_only",
        "tariffs": [0.3, 0.1, 0.2, 0.4],
        "base_load_kw": [0] * 4,
        "chargers": [{"id": "C1", "kw": 1}, {"id": "C2", "kw": 1}],
        "vehicles": [
            {
                "id": f"V{i + 1}",
                "arrival": i,
                "deadline": i + 2,
                "kwh": 0.5,
                "max_kw": 1,
                "compatible": ["C1", "C2"],
            }
            for i in range(3)
        ],
        "assumptions": {
            "provenance": "Constructed six-bit circuit-scale demonstration; not the six-van operational benchmark."
        },
    }
    entry = {"id": d["scenario_id"], "scenario": d, "runs": {}}
    for label, backend in [
        ("full_classical", "highs"),
        ("same_menu_classical", "highs"),
        ("opt_qubo", "qpiai_qubo"),
        ("qcloud_qaoa", "qcloud_qaoa"),
    ]:
        request = dict(d, backend=backend)
        if label != "full_classical":
            request["profile_limit"] = 2
        r = run(request)
        entry["runs"][label] = r
        print(label, r["status"], r.get("incremental_bill"), flush=True)
    entry["runs"]["earliest_departure"] = greedy(d)
    path = Path("artifacts/shipping/quantum_demo.json")
    path.write_text(json.dumps(entry, indent=2))


if __name__ == "__main__":
    main()
