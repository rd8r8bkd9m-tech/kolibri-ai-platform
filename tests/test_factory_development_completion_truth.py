from __future__ import annotations

import copy
import http.client
import importlib.util
import json
import sys
import threading
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE_COMMIT = "7" * 40
REPOSITORY = "rd8r8bkd9m-tech/kolibri-ai-platform"


def load_control(name: str):
    path = ROOT / "ops" / "factory_control.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def leased_development_task(control, *, complete_contract: bool) -> tuple[dict, dict]:
    envelope = {
        "task_id": "KOL-DEV-TRUTH-GATE-1",
        "idempotency_key": "dev-truth-gate-1",
        "kind": "owner_remote_task",
        "objective": "Review the repository contract and return an objective verdict.",
    }
    if complete_contract:
        envelope.update({
            "execution_contract": control.DEVELOPMENT_TASK_CONTRACT,
            "repository": REPOSITORY,
            "base_commit": BASE_COMMIT,
        })
    task = control.normalize_task(envelope)
    task.update({
        "state": control.STATE_LEASED,
        "attempt": 1,
        "attempt_id": "KOL-DEV-TRUTH-GATE-1-attempt-1",
        "fencing_token": 1,
        "lease_owner": "home:agent-host-home",
    })
    reference = "/var/lib/kolibri-agent/artifacts/KOL-DEV-TRUTH-GATE-1/result.json"
    body = {
        "attempt_id": task["attempt_id"],
        "fencing_token": task["fencing_token"],
        "node_id": "home",
        "agent_id": "agent-host-home",
        "result_reference": reference,
        "result": {
            "status": "completed",
            "task_id": task["task_id"],
            "attempt_id": task["attempt_id"],
            "fencing_token": task["fencing_token"],
            "node_id": "home",
            "agent_id": "agent-host-home",
            "result_path": reference,
            "repository": REPOSITORY,
            "base_commit": BASE_COMMIT,
            "objective_verdict": "passed",
            "required_artifacts_missing": [],
        },
    }
    return task, body


def test_development_completion_requires_repository_commit_and_objective_verdict():
    control = load_control("factory_control_development_truth_unit")
    task, body = leased_development_task(control, complete_contract=False)
    body["result"].update({
        "repository": "",
        "base_commit": "",
        "objective_verdict": "",
        "response": "The repository is absent. Verdict: FAIL",
    })

    _evidence, verifier = control.verify_task_completion(
        task, body["result"], body, body["result_reference"],
    )

    assert verifier["verdict"] == "failed"
    assert set(verifier["failed_checks"]) >= {
        "development_contract",
        "development_repository",
        "development_base_commit",
        "development_objective_verdict",
    }


def test_development_completion_accepts_matching_structured_evidence_only():
    control = load_control("factory_control_development_truth_pass")
    task, body = leased_development_task(control, complete_contract=True)

    _evidence, verifier = control.verify_task_completion(
        task, body["result"], body, body["result_reference"],
    )
    assert verifier["verdict"] == "passed"
    assert verifier["checks"]["development_contract"] is True
    assert verifier["checks"]["development_repository"] is True
    assert verifier["checks"]["development_base_commit"] is True
    assert verifier["checks"]["development_objective_verdict"] is True

    blocked = copy.deepcopy(body)
    blocked["result"]["blocked_reason"] = "repository_checkout_missing"
    _evidence, blocked_verifier = control.verify_task_completion(
        task, blocked["result"], blocked, blocked["result_reference"],
    )
    assert blocked_verifier["verdict"] == "failed"
    assert "development_not_blocked" in blocked_verifier["failed_checks"]


def test_external_provider_admits_only_complete_development_source_contract():
    control = load_control("factory_control_development_provider_contract")
    task, _body = leased_development_task(control, complete_contract=True)
    task["envelope"].update({
        "target_node": "home-codex-provider",
        "required_capability": "runner:codex",
        "runner": "codex",
        "write_scope": [],
        "constraints": {
            "read_only": True,
            "max_wall_seconds": 180,
            "network": "provider_managed_only",
        },
        "max_attempts": 1,
        "fallback_allowed": False,
        "source": {
            "kind": "kolibri_provider_gateway",
            "control_plane": "home",
            "response_id": task["task_id"],
            "identity_contract": "kolibri.public-identity.v1",
        },
    })

    assert control.external_provider_task_compatible(
        task, "home-codex-provider", "codex",
    ) is True

    missing_commit = copy.deepcopy(task)
    del missing_commit["envelope"]["base_commit"]
    assert control.external_provider_task_compatible(
        missing_commit, "home-codex-provider", "codex",
    ) is False

    mutable_ref = copy.deepcopy(task)
    mutable_ref["envelope"]["base_commit"] = "main"
    assert control.external_provider_task_compatible(
        mutable_ref, "home-codex-provider", "codex",
    ) is False


def test_http_rejects_false_development_completion_without_mutating_terminal_state(monkeypatch):
    control = load_control("factory_control_development_truth_http")
    task, body = leased_development_task(control, complete_contract=False)
    body["result"].update({
        "repository": "",
        "base_commit": "",
        "objective_verdict": "failed",
        "response": "Verdict: FAIL — repository is absent",
    })
    tasks = {task["task_id"]: copy.deepcopy(task)}
    monkeypatch.setattr(control, "load_task", lambda task_id: copy.deepcopy(tasks.get(task_id)))
    monkeypatch.setattr(
        control,
        "save_task",
        lambda value: tasks.__setitem__(value["task_id"], copy.deepcopy(value)),
    )
    monkeypatch.setattr(control, "get_json", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        control,
        "require_external_provider_actor_auth",
        lambda *_args, **_kwargs: True,
    )

    server = control.ThreadingHTTPServer(("127.0.0.1", 0), control.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        connection = http.client.HTTPConnection(host, port, timeout=2)
        connection.request(
            "POST",
            f"/v1/tasks/{task['task_id']}/complete",
            body=json.dumps(body),
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        payload = json.loads(response.read())
        connection.close()

        assert response.status == 409
        assert payload["error"] == "completion_verification_failed"
        assert "development_objective_verdict" in payload["verifier"]["failed_checks"]
        assert tasks[task["task_id"]]["state"] == control.STATE_LEASED
        assert tasks[task["task_id"]].get("truth_gate") is None
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
