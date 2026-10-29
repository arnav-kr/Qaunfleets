"""Per-request text evidence, derived from actual results rather than progress claims."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / "artifacts/run_logs"


def _redact(value):
    secrets = dict(dotenv_values(ROOT / ".env"))
    secrets.update(os.environ)
    tokens = [
        v
        for k, v in secrets.items()
        if any(s in k.lower() for s in ("key", "token", "password", "secret"))
        and isinstance(v, str)
        and len(v) >= 8
    ]

    def clean(item):
        if isinstance(item, dict):
            return {
                k: "[REDACTED]"
                if any(s in k.lower() for s in ("api_key", "password", "token", "secret"))
                else clean(v)
                for k, v in item.items()
            }
        if isinstance(item, list):
            return [clean(v) for v in item]
        if isinstance(item, str):
            for token in tokens:
                item = item.replace(token, "[REDACTED]")
        return item

    return clean(value)


def run_logged(operation, request, execute):
    """Persist input before execution and sanitized outputs/errors afterwards."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:12]
    path = LOG_DIR / f"{run_id}.txt"
    with path.open("x", encoding="utf-8") as log:

        def write(label, value):
            stamp = datetime.now(timezone.utc).isoformat()
            log.write(f"{stamp} [{label}]\n")
            log.write(json.dumps(_redact(value), indent=2, ensure_ascii=True) + "\n\n")
            log.flush()
            summary = {
                k: v
                for k, v in value.items()
                if k
                in (
                    "operation",
                    "source",
                    "backend",
                    "shots",
                    "qubits",
                    "circuits",
                    "provider",
                    "execution_mode",
                    "method",
                    "status",
                    "validated",
                    "independent_validation",
                    "capacity_violations",
                    "confirmed_compliance",
                    "error_type",
                    "message",
                )
            }
            if "attempts" in value:
                summary["solver_terminations"] = [
                    item.get("solver", {}).get("termination") for item in value["attempts"]
                ]
            print(f"[{run_id}] {label} {json.dumps(_redact(summary))}", flush=True)

        write("REQUEST", {"run_id": run_id, "operation": operation, "input": request})
        try:
            response = execute(request)
        except Exception as error:
            write("FAILED", {"error_type": type(error).__name__, "message": str(error)})
            raise
        result = response["result"] if operation == "/replan" else response
        forecast = result.get("forecast_evidence", {})
        write("FORECAST RESULT", forecast)
        evidence = result.get("execution_evidence", {})
        # Input matrices already belong to recorded benchmark evidence. Retain every
        # solver attempt's actual solution/status without duplicating large models.
        write(
            "OPTIMIZER RESULT",
            {
                k: [{a: b for a, b in item.items() if a != "model"} for item in v]
                if k == "attempts"
                else v
                for k, v in evidence.items()
                if k != "profile_menu"
            },
        )
        write(
            "APPLICATION RESULT",
            {
                k: result[k]
                for k in (
                    "status",
                    "scenario_sha256",
                    "validated",
                    "independent_validation",
                    "validation_report",
                    "capacity_violations",
                    "confirmed_compliance",
                    "incremental_bill",
                    "energy_cost",
                    "incremental_demand_charge",
                    "peak_kw",
                    "schedule",
                    "forecasts",
                    "replay",
                    "reasons",
                )
                if k in result
            },
        )
        write("COMPLETED", {"run_id": run_id, "operation": operation})
    return response
