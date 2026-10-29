"""Local runtime configuration shared by the SDK adapters."""

import os
import sys
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent


def api_key(name: str) -> str:
    value = os.environ.get(name) or dotenv_values(ROOT / ".env").get(name)
    if not value or value == "replace-locally":
        raise ValueError(f"Set {name} in the environment or local .env file")
    return value


def quantum_python() -> str:
    return os.environ.get("QAUNFLEETS_QUANTUM_PYTHON", sys.executable)
