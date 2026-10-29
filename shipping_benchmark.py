"""Recorded product runs, same-menu and full-menu references; no claimed speedup."""

import json
import time
from pathlib import Path

from depot_reference import greedy
from product_pipeline import run

ROOT = Path(__file__).parent
OUT = ROOT / "artifacts/shipping"


def main():
    OUT.mkdir(exist_ok=True, parents=True)
    report = {"created_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "cases": [], "four_way": []}
    for name in [
        "normal_flat",
        "tariff_and_peak",
        "prestart_outage_derating",
        "impossible_departure",
    ]:
        d = json.loads((ROOT / f"data/scenarios/depot-v1/{name}.json").read_text())
        entry = {"id": name, "scenario": d, "runs": {}}
        for label, backend, limit in [
            ("full_classical", "highs", None),
            ("same_menu_classical", "highs", 4),
            ("opt_qubo", "qpiai_qubo", 4),
        ]:
            request = dict(d, backend=backend, forecast_source="none")
            if limit:
                request["profile_limit"] = limit
            r = run(request)
            entry["runs"][label] = r
            print(name, label, r["status"], r.get("incremental_bill"), flush=True)
        entry["runs"]["earliest_departure"] = greedy(d)
        report["cases"].append(entry)
        (OUT / "benchmark.json").write_text(json.dumps(report, indent=2))
    # Same deterministic menu and same soft-risk weight, changing one component at a time.
    d = json.loads((ROOT / "data/scenarios/depot-v1/tariff_and_peak.json").read_text())
    for source in ["classical", "qcloud"]:
        bundle = None
        for backend in ["highs", "qpiai_qubo"]:
            request = dict(
                d, backend=backend, profile_limit=4, forecast_source=source, risk_weight=0.25
            )
            r = run(request, forecast_bundle=bundle)
            if source == "qcloud":
                bundle = r["forecast_evidence"]
            report["four_way"].append(
                {"forecast": source, "optimizer": backend, "scenario": request, "result": r}
            )
            print("four-way", source, backend, r["status"], r.get("incremental_bill"), flush=True)
            (OUT / "benchmark.json").write_text(json.dumps(report, indent=2))
    report["four_way_note"] = (
        "Integration smoke tests; the identical saved QCloud feature draw is reused for both optimizers. Same menu within each predictor pair. Not a statistical prediction-quality or quantum-advantage experiment."
    )
    (OUT / "benchmark.json").write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
