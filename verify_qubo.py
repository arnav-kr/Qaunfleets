"""Exhaustively check QUBO mathematics; validate real Opt benchmarks separately."""

import itertools
import json
from pathlib import Path

import numpy as np

from qubo_scheduler import build_qubo, slack_weights, valid_selection


def main():
    checks = []
    for k in range(25):
        w = slack_weights(k)
        assert {
            sum(a * b for a, b in zip(bits, w)) for bits in itertools.product([0, 1], repeat=len(w))
        } == set(range(k + 1))
    checks.append("Bounded slack exactly represents every integer 0..K for K=0..24")
    # Three cars can overload a feeder although every pair fits: catches pair-only encodings.
    d = {"vehicles": [{}, {}, {}], "tariffs": [0.1, 0.2], "base_load_kw": [0, 0], "capacity_kw": 2}
    profiles = [
        (v, v, t, t + 1, np.array([1.0, 0.0] if t == 0 else [0.0, 1.0]), 0.1 + 0.1 * t)
        for v in range(3)
        for t in range(2)
    ]
    for cap in [1, 2, 3]:
        d["capacity_kw"] = cap
        m = build_qubo(d, profiles, cap)
        best = {}
        for bits in itertools.product([0, 1], repeat=len(m["names"])):
            value = m["offset"] + sum(q * bits[i] * bits[j] for (i, j), q in m["q"].items())
            key = bits[: len(profiles)]
            best[key] = min(best.get(key, float("inf")), value)
        feasible = []
        for bits, value in best.items():
            cost = sum(p[5] * b for p, b in zip(profiles, bits))
            valid = valid_selection(d, profiles, bits, cap)
            assert (abs(value - cost) < 1e-7) == valid, (cap, bits, value, cost)
            if valid:
                feasible.append((value, bits))
        if feasible:
            assert valid_selection(d, profiles, min(best, key=best.get), cap)
        checks.append(
            f"All assignments checked at capacity {cap}: zero penalty iff physically feasible"
        )
    # Different cars sharing a charger must conflict even with ample feeder power.
    conflict = [(0, 0, 0, 1, np.array([1.0, 0.0]), 0.1), (1, 0, 0, 1, np.array([1.0, 0.0]), 0.1)]
    d.update(vehicles=[{}, {}], capacity_kw=3)
    m = build_qubo(d, conflict, 3)
    assert not valid_selection(d, conflict, [1, 1], 3)
    assert m["offset"] + sum(m["q"].values()) > 0.2 + m["penalty"] - 0.00001
    checks.append("Charger conflict cannot be hidden by adequate feeder capacity")
    out = Path("artifacts/shipping")
    out.mkdir(exist_ok=True, parents=True)
    (out / "math_checks.json").write_text(json.dumps({"passed": True, "checks": checks}, indent=2))
    print(json.dumps(checks))


if __name__ == "__main__":
    main()
