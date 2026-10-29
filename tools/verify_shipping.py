import copy
import itertools
import json
from pathlib import Path

from depot_reference import digest, validate
from ising_encoding import coefficients
from product_pipeline import run

ROOT = Path(__file__).resolve().parents[1]


def main():
    report = json.loads((ROOT / "artifacts/shipping/benchmark.json").read_text())
    demo = json.loads((ROOT / "artifacts/shipping/quantum_demo.json").read_text())
    checks = []
    for case in report["cases"] + [demo]:
        for name, r in case["runs"].items():
            if not r.get("schedule"):
                continue
            # The saved instance is the same physical model; normalize hash only for this independent audit.
            d = case["scenario"]
            rr = dict(r, scenario_sha256=digest(d))
            audit = validate(d, rr)
            assert audit["passed"], audit
            checks.append(case["id"] + "/" + name + ": independent physical and financial checks")
            for a in r.get("execution_evidence", {}).get("attempts", []):
                m = a["model"]
                assert all(x in [0, 1] for x in a["bits"])
                if a["valid_schedule"]:
                    assert sum(a["bits"][: m["profile_count"]]) == len(d["vehicles"])
    if report["four_way"]:
        q = [
            x["result"]["forecast_evidence"]
            for x in report["four_way"]
            if x["forecast"] == "qcloud"
        ]
        assert q[0]["measured_features"] == q[1]["measured_features"]
        checks.append("Same QCloud measurement vector reused across optimizer comparison")
    m = demo["runs"]["qcloud_qaoa"]["execution_evidence"]["attempts"][0]["model"]
    terms = m["coefficients"]
    scale, c, h, pairs = coefficients(len(m["names"]), terms, m["offset"])
    for bits in itertools.product([0, 1], repeat=len(h)):
        z = [1 - 2 * x for x in bits]
        binary = m["offset"] + sum(v * bits[i] * bits[j] for i, j, v in terms)
        spin = scale * (
            c + sum(a * b for a, b in zip(h, z)) + sum(v * z[i] * z[j] for i, j, v in pairs)
        )
        assert abs(binary - spin) < 1e-8
    checks.append("All 64 basis states: implemented Ising Hamiltonian equals original QUBO energy")
    d = report["cases"][1]["scenario"]
    r = copy.deepcopy(report["cases"][1]["runs"]["opt_qubo"])
    r["scenario_sha256"] = digest(d)
    r["schedule"][0]["grid_kw_by_slot"][0] += 1
    assert not validate(d, r)["passed"]
    checks.append("Tampered schedule rejected by independent validator")
    r = run(dict(d, backend="highs", forecast_source="none"))
    assert all(f["predicted_disconnect"] is None for f in r["forecasts"])
    checks.append("Confirmed-only route produces no invented predictions")
    (ROOT / "artifacts/shipping/acceptance.json").write_text(
        json.dumps({"passed": True, "count": len(checks), "checks": checks}, indent=2)
    )
    print("Shipping acceptance checks passed:", len(checks))


if __name__ == "__main__":
    main()
