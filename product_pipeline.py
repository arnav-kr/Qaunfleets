"""Product orchestration with explicit forecast source and no hidden solver swap."""

import json
import math
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path

import joblib
import numpy as np

from runtime_config import quantum_python
from scheduler import solve

ROOT = Path(__file__).parent


def run(data, forecast_bundle=None):
    source = data.get("forecast_source", "none")
    predictions = None
    evidence = {"source": source}
    if source not in ("none", "classical", "qcloud"):
        raise ValueError("Unknown forecast_source")
    data = dict(data)
    if source == "none":
        data.update(prediction_mode="confirmed_only", risk_weight=0)
    else:
        rows = []
        origin = datetime.fromisoformat(data["start"])
        slot_hours = float(data["slot_minutes"]) / 60
        if not 1 <= len(data["vehicles"]) <= 30:
            raise ValueError("Provide 1–30 vehicles")
        for vehicle in data["vehicles"]:
            when = origin + timedelta(hours=float(vehicle["arrival"]) * slot_hours)
            hour = when.hour + when.minute / 60
            rows.append(
                [
                    math.sin(2 * math.pi * hour / 24),
                    math.cos(2 * math.pi * hour / 24),
                    math.sin(2 * math.pi * when.weekday() / 7),
                    math.cos(2 * math.pi * when.weekday() / 7),
                    (float(vehicle["deadline"]) - float(vehicle["arrival"])) * slot_hours,
                    float(vehicle["kwh"]),
                ]
            )
        feature_matrix = np.asarray(rows)
        started = time.perf_counter()
        if source == "qcloud" and forecast_bundle is not None:
            evidence = dict(forecast_bundle)
            feature_matrix = np.asarray(evidence["measured_features"])
        elif source == "qcloud":
            config = json.loads((ROOT / "artifacts/four-way/scaler.json").read_text())
            angles = (
                np.clip(
                    (feature_matrix - np.array(config["scaler_mean"]))
                    / np.array(config["scaler_std"]),
                    -3,
                    3,
                )
                * math.pi
                / 3
            ).tolist()
            worker_result = subprocess.run(
                [quantum_python(), str(ROOT / "qcloud_inference_worker.py")],
                input=json.dumps({"angles": angles}),
                capture_output=True,
                text=True,
                timeout=120,
                cwd=ROOT,
            )
            if worker_result.returncode:
                raise ValueError("QCloud inference failed; no classical substitution was made.")
            evidence = json.loads(worker_result.stdout)
            feature_matrix = np.array(evidence.pop("features"))
            evidence.update(source=source, angles=angles, measured_features=feature_matrix.tolist())
        model = joblib.load(
            ROOT
            / (
                "artifacts/four-way/qml.joblib"
                if source == "qcloud"
                else "artifacts/four-way/classical.joblib"
            )
        )
        predicted_offsets = model["point"].predict(feature_matrix)
        early_offsets = model["low"].predict(feature_matrix)
        predictions = [
            {"residual": float(point_offset), "lower": float(early_offset)}
            for point_offset, early_offset in zip(predicted_offsets, early_offsets)
        ]
        data.update(prediction_mode="model", risk_weight=float(data.get("risk_weight", 0.25)))
        evidence.update(
            seconds=time.perf_counter() - started,
            predictions=predictions,
            warning="Workplace unplug-time model applied experimentally to synthetic depot inputs; not validated fleet departure forecasts. Confirmed deadlines remain hard.",
        )
    result = solve(data, predictions)
    result["forecast_evidence"] = evidence
    if result.get("validated"):
        from depot_reference import digest, validate

        checked = dict(data)
        checked.setdefault("base_load_kw", [0] * len(data["tariffs"]))
        checked.setdefault("efficiency", 0.95)
        checked.setdefault("historic_peak_kw", 0)
        checked.setdefault("demand_rate", 0)
        checked["vehicles"] = [
            dict(
                vehicle,
                compatible=vehicle.get("compatible", [c["id"] for c in data["chargers"]]),
                max_kw=vehicle.get("max_kw", 100),
            )
            for vehicle in data["vehicles"]
        ]
        result["scenario_sha256"] = digest(checked)
        audit = validate(checked, result)
        if not audit["passed"]:
            raise ValueError(
                "Independent physical validation failed: " + ", ".join(audit["errors"])
            )
        result["validation_report"] = audit
        result["independent_validation"] = True
    return result
