import json

import pytest

import execution_logging


def test_log_preserves_matching_input_and_actual_solver_status(tmp_path, monkeypatch):
    monkeypatch.setattr(execution_logging, "LOG_DIR", tmp_path)
    monkeypatch.setenv("QPIAI_OPT_API_KEY", "private-test-key")
    request = {"scenario_id": "demo", "api_key": "private-test-key"}
    result = {
        "status": "search_failed",
        "execution_evidence": {
            "execution_mode": "local",
            "attempts": [{"bits": [0, 1], "solver": {"termination": "completed"}}],
        },
    }
    assert execution_logging.run_logged("/solve", request, lambda _: result) is result
    text = next(tmp_path.glob("*.txt")).read_text()
    assert '"scenario_id": "demo"' in text
    assert '"termination": "completed"' in text
    assert '"status": "search_failed"' in text
    assert "private-test-key" not in text
    assert "[COMPLETED]" in text
    assert request["api_key"] == "private-test-key"


def test_failure_is_persisted_redacted_and_reraised(tmp_path, monkeypatch):
    monkeypatch.setattr(execution_logging, "LOG_DIR", tmp_path)
    monkeypatch.setenv("QPIAI_QCLOUD_API_KEY", "private-cloud-key")

    def fail(_):
        raise ValueError("SDK failed private-cloud-key")

    with pytest.raises(ValueError):
        execution_logging.run_logged("/solve", {}, fail)
    text = next(tmp_path.glob("*.txt")).read_text()
    assert "[FAILED]" in text and "[COMPLETED]" not in text
    assert "private-cloud-key" not in text


def test_replay_logs_reused_forecast_and_separate_files(tmp_path, monkeypatch):
    monkeypatch.setattr(execution_logging, "LOG_DIR", tmp_path)
    response = {"scenario": {}, "result": {"forecast_evidence": {"reused_at_event": True}}}
    for _ in range(2):
        execution_logging.run_logged("/replan", {}, lambda _: response)
    logs = list(tmp_path.glob("*.txt"))
    assert len(logs) == 2
    for path in logs:
        text = path.read_text()
        assert '"reused_at_event": true' in text
        request = text.split("[REQUEST]\n", 1)[1].split("\n\n", 1)[0]
        assert json.loads(request)["operation"] == "/replan"
