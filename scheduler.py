"""General finite-profile classical MILP with independent physical validation."""

import math
import time
from datetime import datetime, timedelta
from pathlib import Path

import joblib
import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix


def finite(x, name, minimum=0):
    x = float(x)
    if not math.isfinite(x) or x < minimum:
        raise ValueError(f"{name} must be finite and >= {minimum}")
    return x


def solve(data, predictions=None):
    start = time.perf_counter()
    dt = finite(data.get("slot_minutes", 30), "slot minutes", 1) / 60
    if dt > 1:
        raise ValueError("Slots must be at most 60 minutes")
    tariffs = np.array([finite(x, "tariff") for x in data["tariffs"]])
    n = len(tariffs)
    if not 1 <= n <= 96:
        raise ValueError("Provide 1–96 tariff slots")
    capacity = finite(data["capacity_kw"], "capacity", 0.01)
    base = np.array([finite(x, "base load") for x in data.get("base_load_kw", [0] * n)])
    if len(base) != n:
        raise ValueError("Base load and tariffs must have identical lengths")
    historic = finite(data.get("historic_peak_kw", 0), "historic peak")
    demand = finite(data.get("demand_rate", 0), "demand rate")
    efficiency = finite(data.get("efficiency", 0.95), "efficiency", 0.01)
    if efficiency > 1:
        raise ValueError("Efficiency must not exceed 1")
    risk = finite(data.get("risk_weight", 0), "risk weight")
    origin = datetime.fromisoformat(data["start"])
    chargers = data["chargers"]
    vehicles = data["vehicles"]
    if not 1 <= len(vehicles) <= 30 or not 1 <= len(chargers) <= 20:
        raise ValueError("Supported demo scope: 1–30 vehicles and 1–20 chargers")
    if len({v["id"] for v in vehicles}) != len(vehicles) or len({c["id"] for c in chargers}) != len(
        chargers
    ):
        raise ValueError("Identifiers must be unique")
    rates = [finite(c["kw"], "charger kW", 0.01) for c in chargers]
    prediction_mode = data.get("prediction_mode", "confirmed_only")
    if prediction_mode not in ("model", "confirmed_only"):
        raise ValueError("prediction_mode must be model or confirmed_only")
    if prediction_mode == "confirmed_only" and (risk != 0 or predictions is not None):
        raise ValueError("confirmed_only requires zero forecast risk and no supplied predictions")
    model = (
        joblib.load(Path(__file__).parent / "artifacts/classical/predictor.joblib")
        if prediction_mode == "model" and predictions is None
        else None
    )
    profiles = []
    forecasts = []
    problems = []
    specs = []
    for i, v in enumerate(vehicles):
        a = finite(v["arrival"], "arrival")
        d = finite(v["deadline"], "deadline")
        e = finite(v["kwh"], "required battery energy", 0.01)
        maxkw = finite(v.get("max_kw", 100), "vehicle rate", 0.01)
        if a != int(a) or d != int(d) or not 0 <= a < d <= n:
            raise ValueError("Arrival/deadline must be integer slot boundaries inside the horizon")
        a = int(a)
        d = int(d)
        specs.append((a, d, e, maxkw))
        when = origin + timedelta(hours=a * dt)
        hour = when.hour + when.minute / 60
        x = [
            [
                math.sin(2 * math.pi * hour / 24),
                math.cos(2 * math.pi * hour / 24),
                math.sin(2 * math.pi * when.weekday() / 7),
                math.cos(2 * math.pi * when.weekday() / 7),
                (d - a) * dt,
                e,
            ]
        ]
        residual = (
            0.0
            if prediction_mode == "confirmed_only"
            else float(model["point"].predict(x)[0])
            if predictions is None
            else predictions[i]["residual"]
        )
        predicted = origin + timedelta(hours=d * dt, minutes=residual)
        correction = (
            0.0
            if prediction_mode == "confirmed_only"
            else float(model["low"].predict(x)[0]) - model["interval_adjustment_minutes"]
            if predictions is None
            else predictions[i]["lower"]
        )
        preferred = max(a, min(d, d + correction / (60 * dt)))
        forecasts.append(
            {
                "vehicle": v["id"],
                "predicted_disconnect": None
                if prediction_mode == "confirmed_only"
                else max(when, predicted).isoformat(),
                "preferred_finish_slot": preferred,
                "confirmed_deadline": (origin + timedelta(hours=d * dt)).isoformat(),
                "source": prediction_mode,
            }
        )
        compatible = v.get("compatible", [c["id"] for c in chargers])
        before = len(profiles)
        for j, c in enumerate(chargers):
            if c["id"] not in compatible:
                continue
            kw = min(rates[j], maxkw)
            slots = math.ceil(e / (efficiency * kw * dt) - 1e-10)
            for s in range(a, d - slots + 1):
                load = np.zeros(n)
                remaining = e / efficiency
                for t in range(s, s + slots):
                    load[t] = min(kw, remaining / dt)
                    remaining -= load[t] * dt
                if np.any(load + base > capacity + 1e-8):
                    continue
                profiles.append(
                    (
                        i,
                        j,
                        s,
                        s + slots,
                        load,
                        float(load @ tariffs * dt) + risk * max(0, s + slots - preferred) * dt,
                    )
                )
        if before == len(profiles):
            problems.append(
                f"{v['id']}: no compatible charging visit fits its energy, deadline and available feeder capacity"
            )
    if np.any(base > capacity + 1e-8):
        problems.append("Background load alone exceeds feeder capacity")
    if problems:
        return {"status": "infeasible", "reasons": problems, "schedule": [], "forecasts": forecasts}
    full_profile_count = len(profiles)
    if data.get("profile_limit") is not None:
        from qubo_scheduler import reduce_profiles

        profiles = reduce_profiles(profiles, len(vehicles), int(data["profile_limit"]), data)
    p = len(profiles)
    if p > 20000:
        raise ValueError("Too many profiles; shorten the horizon or reduce fleet size")
    rows = len(vehicles) + len(chargers) * n + 2 * n
    A = lil_matrix((rows, p + 1))
    lower = np.full(rows, -np.inf)
    upper = np.zeros(rows)
    lower[: len(vehicles)] = 1
    upper[: len(vehicles)] = 1
    offset = len(vehicles)
    upper[offset : offset + len(chargers) * n] = 1
    power = offset + len(chargers) * n
    upper[power : power + n] = capacity - base
    upper[power + n :] = -base
    c = np.zeros(p + 1)
    for k, (i, j, s, end, load, cost) in enumerate(profiles):
        A[i, k] = 1
        A[offset + j * n + s : offset + j * n + end, k] = 1
        A[power : power + n, k] = load.reshape(-1, 1)
        A[power + n :, k] = load.reshape(-1, 1)
        c[k] = cost
    A[power + n :, -1] = -np.ones((n, 1))
    c[-1] = demand
    lo = np.zeros(p + 1)
    hi = np.ones(p + 1)
    lo[-1] = historic
    hi[-1] = max(historic, capacity)
    backend = data.get("backend", "qpiai")
    if backend in ("qpiai_qubo", "qcloud_qaoa"):
        from qubo_scheduler import solve_profiles

        result = solve_profiles(data, profiles)
    elif backend == "qpiai":
        from opt_backend import solve_matrix

        result = solve_matrix(c, A, lower, upper, lo, hi)
    elif backend == "highs":
        result = milp(
            c,
            integrality=np.r_[np.ones(p), 0],
            bounds=Bounds(lo, hi),
            constraints=LinearConstraint(A.tocsr(), lower, upper),
            options={"time_limit": 20, "mip_rel_gap": 1e-7},
        )
    else:
        raise ValueError("backend must be qpiai_qubo, qcloud_qaoa, qpiai or highs")
    if result.x is None:
        return {
            "status": "infeasible" if result.status == 2 else "solver_limit",
            "reasons": [
                "No feasible selection of compatible charging visits satisfies all commitments."
                if result.status == 2
                else "Solver stopped without a feasible schedule; this does not prove infeasibility."
            ],
            "schedule": [],
            "forecasts": forecasts,
            "execution_evidence": getattr(result, "evidence", {}),
        }
    selected = [profiles[k] for k in range(p) if result.x[k] > 0.5]
    # Recompute all physical checks from selected source profiles.
    load = np.zeros(n)
    occupancy = np.zeros((len(chargers), n))
    seen = set()
    schedule = []
    for i, j, s, end, slot_load, cost in selected:
        a, d, e, maxkw = specs[i]
        assert i not in seen and a <= s < end <= d
        seen.add(i)
        assert chargers[j]["id"] in vehicles[i].get("compatible", [ch["id"] for ch in chargers])
        assert max(slot_load) <= min(rates[j], maxkw) + 1e-6
        assert abs(sum(slot_load) * dt * efficiency - e) < 1e-5
        occupancy[j, s:end] += 1
        load += slot_load
        schedule.append(
            {
                "vehicle": vehicles[i]["id"],
                "charger": chargers[j]["id"],
                "start": (origin + timedelta(hours=s * dt)).isoformat(),
                "end": (origin + timedelta(hours=end * dt)).isoformat(),
                "battery_kwh": e,
                "grid_kwh": sum(slot_load) * dt,
                "grid_kw_by_slot": slot_load.tolist(),
                "start_slot": s,
                "end_slot": end,
            }
        )
    assert (
        len(seen) == len(vehicles)
        and max(occupancy.flat) <= 1
        and np.all(load + base <= capacity + 1e-5)
    )
    energy = float(load @ tariffs * dt)
    peak = float(max(load + base))
    increment = demand * (max(historic, peak) - max(historic, float(max(base))))
    return {
        "status": "optimal"
        if result.status == 0
        else "feasible_heuristic"
        if backend in ("qpiai_qubo", "qcloud_qaoa")
        else "feasible_time_limit",
        "schedule": schedule,
        "forecasts": forecasts,
        "aggregate_ev_kw": load.tolist(),
        "aggregate_site_kw": (load + base).tolist(),
        "soft_preference_cost": float(sum(x[5] for x in selected) - energy),
        "optimization_objective": float(sum(x[5] for x in selected) + increment),
        "energy_cost": energy,
        "incremental_demand_charge": increment,
        "incremental_bill": energy + increment,
        "peak_kw": peak,
        "capacity_violations": 0,
        "confirmed_compliance": 1,
        "validated": True,
        "profiles": p,
        "full_profiles": full_profile_count,
        "solver": {
            "qpiai": "QpiAI Opt local MILP",
            "highs": "SciPy HiGHS reference",
            "qpiai_qubo": "QpiAI Opt local QUBO",
            "qcloud_qaoa": "QCloud local QAOA",
        }[backend],
        "execution_evidence": getattr(result, "evidence", {}),
        "mip_gap": None if result.mip_gap is None else float(result.mip_gap),
        "seconds": time.perf_counter() - start,
        "scope": "Optimality applies only to the generated visit menu. QUBO annealing is heuristic. One contiguous visit per vehicle; confirmed commitments stay hard.",
    }


EXAMPLE = {
    "start": "2026-10-29T08:00:00",
    "slot_minutes": 30,
    "capacity_kw": 14,
    "historic_peak_kw": 10,
    "demand_rate": 8,
    "efficiency": 0.95,
    "risk_weight": 1,
    "tariffs": [0.3, 0.3, 0.25, 0.25, 0.15, 0.15, 0.12, 0.12, 0.3, 0.3, 0.4, 0.4],
    "base_load_kw": [2] * 12,
    "chargers": [{"id": "C1", "kw": 7.2}, {"id": "C2", "kw": 7.2}],
    "vehicles": [
        {"id": "EV1", "arrival": 0, "deadline": 8, "kwh": 10, "max_kw": 7.2},
        {"id": "EV2", "arrival": 1, "deadline": 10, "kwh": 8, "max_kw": 7.2},
        {"id": "EV3", "arrival": 3, "deadline": 12, "kwh": 6, "max_kw": 7.2},
    ],
}
