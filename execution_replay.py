"""Slot-boundary execution replay with immutable history and future-only scheduling."""

import math
from copy import deepcopy
from datetime import datetime, timedelta

from scheduler import solve

TOLERANCE = 1e-5


def timestamp(scenario, slot):
    return (
        datetime.fromisoformat(scenario["start"])
        + timedelta(minutes=slot * scenario["slot_minutes"])
    ).isoformat()


def visits(plan):
    return [segment for row in plan.get("schedule", []) for segment in row.get("segments", [row])]


def replay_audit(scenario, rows):
    horizon = len(scenario["tariffs"])
    hours = scenario["slot_minutes"] / 60
    occupancy = {}
    load = [0.0] * horizon
    errors = []
    service = []
    chargers = {c["id"]: c for c in scenario["chargers"]}
    for vehicle in scenario["vehicles"]:
        row = next(r for r in rows if r["vehicle"] == vehicle["id"])
        departure = vehicle.get("actual_departure", vehicle["deadline"])
        for slot, power in enumerate(row["grid_kw_by_slot"]):
            if not math.isfinite(power) or power < 0:
                errors.append("Invalid power")
            if power <= TOLERANCE:
                continue
            charger = row["charger_by_slot"][slot]
            if charger not in chargers or charger not in vehicle.get("compatible", chargers):
                errors.append("Incompatible charger")
                continue
            if not vehicle["arrival"] <= slot < min(departure, vehicle["deadline"]):
                errors.append("Power outside availability")
            if power > min(chargers[charger]["kw"], vehicle.get("max_kw", 100)) + TOLERANCE:
                errors.append("Power above rating")
            key = (charger, slot)
            occupancy[key] = occupancy.get(key, 0) + 1
            if occupancy[key] > 1:
                errors.append("Charger overlap")
            if any(
                b["charger"] == charger and b["start"] <= slot < b["end"]
                for b in scenario.get("charger_blocks", [])
            ):
                errors.append("Occupied charger used")
            load[slot] += power
        energy = sum(row["grid_kw_by_slot"]) * hours * scenario["efficiency"]
        if energy > vehicle["kwh"] + TOLERANCE:
            errors.append("Overdelivery")
        service.append(
            {
                "vehicle": vehicle["id"],
                "required_kwh": vehicle["kwh"],
                "planned_delivered_kwh": energy,
                "shortfall_kwh": max(0, vehicle["kwh"] - energy),
            }
        )
    site = [a + b for a, b in zip(load, scenario["base_load_kw"])]
    violations = sum(p > scenario["capacity_kw"] + TOLERANCE for p in site)
    if violations:
        errors.append("Site capacity exceeded (including background demand)")
    return {
        "passed": not errors,
        "errors": sorted(set(errors)),
        "confirmed_ready": sum(s["shortfall_kwh"] < TOLERANCE for s in service),
        "mandatory_vehicles": len(service),
        "capacity_violations": violations,
        "service": service,
        "aggregate_ev_kw": load,
        "aggregate_site_kw": site,
    }


def replan(request):
    scenario = deepcopy(request["scenario"])
    previous = request["result"]
    now = request["slot"]
    horizon = len(scenario["tariffs"])
    if not isinstance(now, int) or not previous.get("replay", {}).get("slot", 0) <= now < horizon:
        raise ValueError("Event slot must be inside the horizon and cannot precede the last event")
    hours = scenario["slot_minutes"] / 60
    old_rows = {r["vehicle"]: r for r in previous.get("schedule", [])}
    event = deepcopy(request["event"])
    kind = event["type"]
    vehicle_map = {v["id"]: v for v in scenario["vehicles"]}
    if kind in ("depart_now", "deadline"):
        vehicle = vehicle_map[event["vehicle"]]
        if not vehicle["arrival"] <= now < vehicle.get("actual_departure", vehicle["deadline"]):
            raise ValueError("Choose a vehicle currently at the depot")
        if kind == "depart_now":
            vehicle["actual_departure"] = now
        else:
            deadline = event["deadline"]
            if not isinstance(deadline, int) or not now < deadline <= vehicle["deadline"]:
                raise ValueError(
                    "Revised departure must be after now and no later than the current deadline"
                )
            vehicle["deadline"] = deadline
    elif kind == "occupied":
        charger = event["charger"]
        end = event["until"]
        if (
            charger not in {c["id"] for c in scenario["chargers"]}
            or not isinstance(end, int)
            or not now < end <= horizon
        ):
            raise ValueError("Provide a known charger and a future release slot")
        scenario.setdefault("charger_blocks", []).append(
            {"charger": charger, "start": now, "end": end}
        )
    elif kind == "release":
        charger = event["charger"]
        if charger not in {c["id"] for c in scenario["chargers"]}:
            raise ValueError("Provide a known charger")
        active = [
            b
            for b in scenario.get("charger_blocks", [])
            if b["charger"] == charger and b["start"] <= now < b["end"]
        ]
        if not active:
            raise ValueError("This charger has no active bay hold")
        for block in active:
            block["end"] = now
        scenario["charger_blocks"] = [
            b for b in scenario["charger_blocks"] if b["end"] > b["start"]
        ]
    elif kind == "load":
        delta = float(event["delta_kw"])
        end = event["until"]
        if (
            not math.isfinite(delta)
            or delta < 0
            or not isinstance(end, int)
            or not now < end <= horizon
        ):
            raise ValueError("Provide a nonnegative load increase and a future end slot")
        for slot in range(now, end):
            scenario["base_load_kw"][slot] += delta
    else:
        raise ValueError("Unknown execution event")

    historical = []
    for segment in visits(previous):
        end = min(now, segment["end_slot"])
        if segment["start_slot"] >= end:
            continue
        frozen = deepcopy(segment)
        frozen["end_slot"] = end
        frozen["grid_kw_by_slot"] = segment["grid_kw_by_slot"][:now] + [0.0] * (horizon - now)
        historical.append(frozen)
    delivered = {
        v["id"]: sum(old_rows.get(v["id"], {}).get("grid_kw_by_slot", [0] * horizon)[:now])
        * hours
        * scenario["efficiency"]
        for v in scenario["vehicles"]
    }
    future = deepcopy(scenario)
    future.update(
        start=timestamp(scenario, now),
        tariffs=scenario["tariffs"][now:],
        base_load_kw=scenario["base_load_kw"][now:],
        backend=scenario.get("backend", "qpiai_qubo"),
        prediction_mode="confirmed_only",
        risk_weight=0,
    )
    past_peak = max(previous.get("aggregate_site_kw", [])[:now], default=0)
    future["historic_peak_kw"] = max(scenario.get("historic_peak_kw", 0), past_peak)
    future["charger_blocks"] = [
        {"charger": b["charger"], "start": max(0, b["start"] - now), "end": b["end"] - now}
        for b in scenario.get("charger_blocks", [])
        if b["end"] > now
    ]
    future["vehicles"] = [
        dict(
            v,
            arrival=max(0, v["arrival"] - now),
            deadline=v["deadline"] - now,
            kwh=v["kwh"] - delivered[v["id"]],
        )
        for v in scenario["vehicles"]
        if v.get("actual_departure", v["deadline"]) > now
        and v["kwh"] - delivered[v["id"]] > TOLERANCE
    ]
    # Reuse arrival-time preferences; never feed residual energy into an arrival-trained model.
    original_forecasts = {f["vehicle"]: f for f in previous.get("forecasts", [])}
    predictions = []
    for vehicle in future["vehicles"]:
        original_deadline = vehicle_map[vehicle["id"]]["deadline"]
        preference = original_forecasts.get(vehicle["id"], {}).get(
            "preferred_finish_slot", original_deadline
        )
        predictions.append(
            {
                "residual": 0,
                "lower": (min(preference, original_deadline) - original_deadline)
                * scenario["slot_minutes"],
            }
        )
    if predictions:
        future.update(prediction_mode="model", risk_weight=scenario.get("risk_weight", 0.25))
    try:
        outcome = (
            solve(future, predictions or None)
            if future["vehicles"]
            else {"status": "complete", "schedule": [], "seconds": 0}
        )
    except Exception:
        outcome = {
            "status": "solver_error",
            "schedule": [],
            "reasons": ["Event recorded; future solver failed. Future EV charging is held."],
        }
    future_found = not future["vehicles"] or bool(outcome.get("schedule"))
    combined = historical[:]
    for segment in outcome.get("schedule", []):
        shifted = deepcopy(segment)
        shifted["start_slot"] += now
        shifted["end_slot"] += now
        shifted["grid_kw_by_slot"] = [0.0] * now + segment["grid_kw_by_slot"]
        combined.append(shifted)
    rows = []
    for vehicle in scenario["vehicles"]:
        segments = [s for s in combined if s["vehicle"] == vehicle["id"]]
        power = [sum(s["grid_kw_by_slot"][t] for s in segments) for t in range(horizon)]
        charger_slots = [
            next((s["charger"] for s in segments if s["grid_kw_by_slot"][t] > TOLERANCE), None)
            for t in range(horizon)
        ]
        if (
            power[:now]
            != old_rows.get(vehicle["id"], {}).get("grid_kw_by_slot", [0.0] * horizon)[:now]
        ):
            raise ValueError("Execution history changed")
        for segment in segments:
            segment.update(
                start=timestamp(scenario, segment["start_slot"]),
                end=timestamp(scenario, segment["end_slot"]),
            )
        rows.append(
            {
                "vehicle": vehicle["id"],
                "charger": ", ".join(dict.fromkeys(s["charger"] for s in segments)) or "Unassigned",
                "charger_by_slot": charger_slots,
                "segments": segments,
                "grid_kw_by_slot": power,
                "battery_kwh": sum(power) * hours * scenario["efficiency"],
                "grid_kwh": sum(power) * hours,
                "start_slot": min((s["start_slot"] for s in segments), default=now),
                "end_slot": max((s["end_slot"] for s in segments), default=now),
            }
        )
    audit = replay_audit(scenario, rows)
    for service in audit["service"]:
        vehicle = vehicle_map[service["vehicle"]]
        service["delivered_so_far_kwh"] = delivered[vehicle["id"]]
        service["departed"] = vehicle.get("actual_departure", vehicle["deadline"]) <= now
        service["realized_shortfall_kwh"] = (
            max(0, vehicle["kwh"] - delivered[vehicle["id"]]) if service["departed"] else 0
        )
    energy_cost = sum(
        p * price * hours for p, price in zip(audit["aggregate_ev_kw"], scenario["tariffs"])
    )
    peak = max(audit["aggregate_site_kw"])
    historic = scenario.get("historic_peak_kw", 0)
    demand = scenario.get("demand_rate", 0) * (
        max(historic, peak) - max(historic, max(scenario["base_load_kw"]))
    )
    realized_cost = sum(
        p * price * hours
        for p, price in zip(audit["aggregate_ev_kw"][:now], scenario["tariffs"][:now])
    )
    compliant = audit["passed"] and audit["confirmed_ready"] == len(rows)
    result = dict(
        outcome,
        schedule=rows,
        forecasts=previous.get("forecasts", []),
        forecast_evidence=dict(previous.get("forecast_evidence", {}), reused_at_event=True),
        aggregate_ev_kw=audit["aggregate_ev_kw"],
        aggregate_site_kw=audit["aggregate_site_kw"],
        energy_cost=energy_cost,
        incremental_demand_charge=demand,
        incremental_bill=energy_cost + demand,
        peak_kw=peak,
        capacity_violations=audit["capacity_violations"],
        confirmed_compliance=audit["confirmed_ready"] / len(rows),
        validated=compliant,
        independent_validation=audit["passed"],
        validation_report=audit,
        status="replanned" if compliant else "service_shortfall" if future_found else "safe_hold",
        replay={
            "slot": now,
            "event": event,
            "events": previous.get("replay", {}).get("events", []) + [dict(event, slot=now)],
            "delivered_kwh": delivered,
            "realized_energy_cost": realized_cost,
            "historical_peak_kw": past_peak,
            "future_plan_found": future_found,
            "future_solver_status": outcome["status"],
            "execution_slot_origin": now,
            "service": audit["service"],
            "policy": "Staffed depot; relocation at slot boundaries. Explicit occupied-bay events override charger availability. Fixed rated power, final-slot taper only.",
        },
    )
    result["reasons"] = (
        outcome.get("reasons", [])
        + (
            []
            if compliant
            else ["Not all charging commitments are met. Shortfalls are listed per vehicle."]
        )
        + audit["errors"]
    )
    return {"scenario": scenario, "result": result}
