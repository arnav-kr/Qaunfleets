import json
from pathlib import Path

import pytest

from product_pipeline import run
from runtime_config import api_key

ROOT = Path(__file__).resolve().parents[1]


def test_classical_plan_is_independently_validated():
    scenario = json.loads((ROOT / "data/scenarios/depot-v1/tariff_and_peak.json").read_text())
    result = run(dict(scenario, backend="highs", forecast_source="none"))
    assert result["independent_validation"]
    assert result["confirmed_compliance"] == 1
    assert result["capacity_violations"] == 0
    assert all(row["predicted_disconnect"] is None for row in result["forecasts"])


def test_impossible_departure_is_rejected():
    scenario = json.loads((ROOT / "data/scenarios/depot-v1/impossible_departure.json").read_text())
    result = run(dict(scenario, backend="highs", forecast_source="none"))
    assert result["status"] == "infeasible"
    assert not result["schedule"]


def test_environment_credentials_work_without_a_file(monkeypatch, tmp_path):
    monkeypatch.setattr("runtime_config.ROOT", tmp_path)
    monkeypatch.setenv("QPIAI_OPT_API_KEY", "test-only-placeholder")
    assert api_key("QPIAI_OPT_API_KEY") == "test-only-placeholder"


def test_missing_credentials_are_not_silently_accepted(monkeypatch, tmp_path):
    monkeypatch.setattr("runtime_config.ROOT", tmp_path)
    monkeypatch.delenv("QPIAI_OPT_API_KEY", raising=False)
    with pytest.raises(ValueError, match="Set QPIAI_OPT_API_KEY"):
        api_key("QPIAI_OPT_API_KEY")
