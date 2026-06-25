import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_control():
    spec = importlib.util.spec_from_file_location("factory_control", ROOT / "ops" / "factory_control.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_successful_retry_clears_top_level_error_and_keeps_attempt_history():
    control = load_control()
    task = control.normalize_task({
        "task_id": "RETRY-CLEAR-1",
        "idempotency_key": "retry-clear-1",
        "kind": "read_only_probe",
        "max_retries": 2,
    })
    task["attempt"] = 1
    task["attempt_id"] = "RETRY-CLEAR-1-attempt-1"
    task["state"] = control.STATE_RUNNING
    task["error_type"] = "runtime_error"
    task["error"] = "first attempt failed"
    task["result_reference"] = "/tmp/attempt-1/result.json"
    control.append_attempt_history(task, "failed", task["error_type"], task["error"], task["result_reference"])

    task["attempt"] = 2
    task["attempt_id"] = "RETRY-CLEAR-1-attempt-2"
    task["state"] = control.STATE_RUNNING
    task, result, has_pr = control.apply_task_completion(task, {
        "result": {"status": "completed", "result_path": "/tmp/attempt-2/result.json"},
        "result_reference": "/tmp/attempt-2/result.json",
    })

    assert has_pr is False
    assert result["status"] == "completed"
    assert task["state"] == control.STATE_COMPLETED
    assert task["error_type"] is None
    assert task["error"] is None
    assert task["result_reference"] == "/tmp/attempt-2/result.json"
    assert task["attempt_history"][0]["attempt_id"] == "RETRY-CLEAR-1-attempt-1"
    assert task["attempt_history"][0]["error"] == "first attempt failed"
    assert task["attempt_history"][1]["attempt_id"] == "RETRY-CLEAR-1-attempt-2"
    assert task["attempt_history"][1]["error"] is None
