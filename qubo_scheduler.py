"""Auditable profile QUBO: exact-one, charger conflicts and integer feeder slack.

Peak-ceiling decomposition keeps demand charges out of penalty tuning. No repair,
MILP seed, or hidden fallback is applied to an Opt sample.
"""

import itertools
import math
import time
from functools import reduce
from types import SimpleNamespace

import numpy as np


def reduce_profiles(profiles, n, limit, data=None):
    if not 1 <= limit <= 12:
        raise ValueError("profile_limit must be 1–12")
    selected = []
    seed = {}
    if data is not None:
        load = np.array(data.get("base_load_kw", [0] * len(data["tariffs"])), dtype=float)
        occupied = set()
        for v in sorted(range(n), key=lambda i: data["vehicles"][i]["deadline"]):
            for p in sorted((p for p in profiles if p[0] == v), key=lambda p: (p[2], p[1])):
                keys = {(p[1], t) for t in range(p[2], p[3])}
                if not (keys & occupied) and np.all(load + p[4] <= data["capacity_kw"] + 1e-8):
                    seed[v] = p
                    load += p[4]
                    occupied |= keys
                    break
        if len(seed) != n:
            seed = {}
    for v in range(n):
        candidates = [p for p in profiles if p[0] == v]
        # Deterministic, solver-independent menu: cheap, early, late, then cheap diversity.
        rankings = [
            sorted(candidates, key=lambda p: (p[5], p[2], p[1])),
            sorted(candidates, key=lambda p: (p[2], p[1])),
            sorted(candidates, key=lambda p: (-p[2], p[1])),
        ]
        chosen = [seed[v]] if v in seed else []
        seen = {(p[1], p[2]) for p in chosen}
        for ranking in itertools.cycle(rankings):
            available = [p for p in ranking if (p[1], p[2]) not in seen]
            if not available or len(chosen) >= min(limit, len(candidates)):
                break
            p = available[0]
            chosen.append(p)
            seen.add((p[1], p[2]))
        selected.extend(chosen)
    return selected


def slack_weights(k):
    weights = []
    left = k
    power = 1
    while left > 0:
        w = min(power, left)
        weights.append(w)
        left -= w
        power *= 2
    return weights


def build_qubo(data, profiles, ceiling):
    p = len(profiles)
    names = [f"visit_{k}" for k in range(p)]
    qubo_coefficients = {}
    offset = 0.0
    rows = []
    costs = [float(x[5]) for x in profiles]
    penalty = 1 + sum(
        max(costs[k] for k, x in enumerate(profiles) if x[0] == v)
        for v in range(len(data["vehicles"]))
    )

    def add(i, j, value):
        key = (min(i, j), max(i, j))
        qubo_coefficients[key] = qubo_coefficients.get(key, 0.0) + value

    def square(terms, target):
        nonlocal offset
        offset += penalty * target * target
        for i, w in terms:
            add(i, i, penalty * (w * w - 2 * target * w))
        for (i, w), (j, z) in itertools.combinations(terms, 2):
            add(i, j, 2 * penalty * w * z)

    for k, c in enumerate(costs):
        add(k, k, c)
    for v in range(len(data["vehicles"])):
        square([(k, 1) for k, x in enumerate(profiles) if x[0] == v], 1)
    conflicts = []
    for a, b in itertools.combinations(range(p), 2):
        x, y = profiles[a], profiles[b]
        if x[0] != y[0] and x[1] == y[1] and max(x[2], y[2]) < min(x[3], y[3]):
            add(a, b, penalty)
            conflicts.append([a, b])
    seen = set()
    for t, base in enumerate(data.get("base_load_kw", [0] * len(data["tariffs"]))):
        loads = [float(x[4][t]) for x in profiles]
        raw = [round(x * 1000000) for x in loads]
        if any(abs(x * 1000000 - r) > 1e-4 for x, r in zip(loads, raw)):
            raise ValueError("QUBO requires power representable to 0.000001 kW")
        unit = reduce(math.gcd, raw, 0)
        if not unit:
            continue
        weights = [r // unit for r in raw]
        bound = math.floor((min(data["capacity_kw"], ceiling) - base) * 1000000 / unit + 1e-8)
        if bound < 0:
            return None
        # Maximum under the exact-one constraints; redundant feeder rows need no slack.
        maximum = sum(
            max((weights[k] for k, x in enumerate(profiles) if x[0] == v), default=0)
            for v in range(len(data["vehicles"]))
        )
        if maximum <= bound:
            continue
        signature = (tuple(weights), bound)
        if signature in seen:
            continue
        seen.add(signature)
        terms = [(k, w) for k, w in enumerate(weights) if w]
        slack = []
        # If only pairwise incompatibilities are needed, use exact conflict penalties.
        positive = set(w for w in weights if w)
        if len(positive) == 1 and bound // next(iter(positive)) == 1:
            for (a, _), (b, _) in itertools.combinations(terms, 2):
                add(a, b, penalty)
        elif bound == 0:
            for k, w in terms:
                add(k, k, penalty * w * w)
        else:
            for w in slack_weights(bound):
                variable_index = len(names)
                names.append(f"slack_t{t}_{variable_index}")
                terms.append((variable_index, w))
                slack.append([variable_index, w])
            square(terms, bound)
        rows.append(
            {
                "slot": t,
                "weights": weights,
                "bound": bound,
                "power_unit_kw": unit / 1000000,
                "slack": slack,
            }
        )
    qubo_coefficients = {k: v for k, v in qubo_coefficients.items() if abs(v) > 1e-10}
    if len(names) > 250 or len(qubo_coefficients) > 5000:
        raise ValueError("QUBO exceeds free local limits; reduce profile_limit or horizon")
    return {
        "q": qubo_coefficients,
        "offset": offset,
        "names": names,
        "penalty": penalty,
        "rows": rows,
        "conflicts": conflicts,
        "profile_count": p,
        "ceiling_kw": ceiling,
    }


def valid_selection(data, profiles, bits, ceiling):
    chosen = [k for k in range(len(profiles)) if bits[k] > 0.5]
    if any(sum(profiles[k][0] == v for k in chosen) != 1 for v in range(len(data["vehicles"]))):
        return False
    for a, b in itertools.combinations(chosen, 2):
        x, y = profiles[a], profiles[b]
        if x[1] == y[1] and max(x[2], y[2]) < min(x[3], y[3]):
            return False
    load = sum((profiles[k][4] for k in chosen), np.zeros(len(data["tariffs"]))) + np.array(
        data.get("base_load_kw", [0] * len(data["tariffs"]))
    )
    return bool(np.all(load <= min(data["capacity_kw"], ceiling) + 1e-6))


def solve_profiles(data, profiles):
    from opt_backend import solve_qubo

    started = time.perf_counter()
    base = np.array(data.get("base_load_kw", [0] * len(data["tariffs"])))
    historic = float(data.get("historic_peak_kw", 0))
    capacity = data["capacity_kw"]
    demand = data.get("demand_rate", 0)
    # All attainable per-slot loads from distinct vehicles, ignoring conflicts (safe superset).
    peaks = {round(capacity, 6), round(max(historic, float(max(base))), 6)}
    for t, b in enumerate(base):
        sums = {0.0}
        for v in range(len(data["vehicles"])):
            values = {round(float(x[4][t]), 6) for x in profiles if x[0] == v}
            sums = {round(s + w, 6) for s in sums for w in values if s + w + b <= capacity + 1e-6}
            if len(sums) > 5000:
                raise ValueError("Too many peak levels; use a smaller scenario")
        peaks.update(round(b + s, 6) for s in sums)
    ceilings = sorted(
        x
        for x in peaks
        if max(base) - 1e-6 <= x <= capacity + 1e-6 and x >= min(historic, capacity) - 1e-6
    )
    if not demand:
        ceilings = [capacity]
    if len(ceilings) > 24:
        raise ValueError("More than 24 peak levels; reduce the scenario for this QUBO prototype")
    attempts = []
    best = None
    for ceiling in ceilings:
        model = build_qubo(data, profiles, ceiling)
        if model is None:
            continue
        if data.get("backend") == "qcloud_qaoa":
            from qaoa_adapter import solve_qaoa

            answer = solve_qaoa(model)
        else:
            answer = solve_qubo(model, seed=int(data.get("seed", 7)))
        bits = answer.x
        valid = bits is not None and valid_selection(data, profiles, bits, ceiling)
        public = {k: v for k, v in model.items() if k != "q"}
        public["coefficients"] = [[i, j, v] for (i, j), v in model["q"].items()]
        attempt = {
            "ceiling_kw": ceiling,
            "valid_schedule": bool(valid),
            "bits": None if bits is None else bits.tolist(),
            "model": public,
            "solver": answer.evidence,
        }
        if "samples" in answer.evidence:
            for field in ("samples", "uniform_samples"):
                samples = answer.evidence[field]
                total = sum(s["count"] for s in samples)
                attempt[field + "_feasible_fraction"] = (
                    sum(
                        s["count"]
                        for s in samples
                        if valid_selection(data, profiles, s["bits"], ceiling)
                    )
                    / total
                )
        attempts.append(attempt)
        if valid:
            chosen = [k for k in range(len(profiles)) if bits[k] > 0.5]
            site = base + sum((profiles[k][4] for k in chosen), np.zeros(len(base)))
            score = sum(profiles[k][5] for k in chosen) + demand * (
                max(historic, float(max(site))) - max(historic, float(max(base)))
            )
            attempt["objective"] = score
            if best is None or score < best[0]:
                best = (score, bits[: len(profiles)], float(max(site)), len(attempts) - 1)
    evidence = {
        "provider": "QCloud" if data.get("backend") == "qcloud_qaoa" else "QpiAI Opt",
        "execution_mode": "local",
        "problem_class": "QUBO",
        "quantum_hardware": False,
        "method": "peak-ceiling QUBO sweep",
        "no_repair_or_fallback": True,
        "menu_policy": "Retain feasible EDF visit per vehicle when available; then cheap, early and late alternatives. No exact optimizer used to construct menu.",
        "attempts": attempts,
        "selected_attempt": None if best is None else best[3],
        "total_seconds": time.perf_counter() - started,
        "profile_menu": [
            {
                "bit": k,
                "vehicle": data["vehicles"][x[0]]["id"],
                "charger": data["chargers"][x[1]]["id"],
                "start_slot": x[2],
                "end_slot": x[3],
                "objective_cost": x[5],
            }
            for k, x in enumerate(profiles)
        ],
    }
    return SimpleNamespace(
        x=None if best is None else np.r_[best[1], best[2]],
        status=1,
        mip_gap=None,
        evidence=evidence,
    )
