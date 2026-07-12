from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module():
    path = ROOT / "scripts" / "verify_factory_campaign.py"
    spec = importlib.util.spec_from_file_location("verify_factory_campaign", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def verified_task():
    digest = "a" * 64
    return {
        "state": "completed",
        "attempt_id": "task-attempt-1",
        "fencing_token": 7,
        "lease_owner": "worker:agent-host-worker",
        "result_reference": "/immutable/result.json",
        "result": {"status": "completed", "fencing_token": 7},
        "envelope": {"target_node": "worker"},
        "completion_evidence": {
            "attempt_id": "task-attempt-1",
            "fencing_token": 7,
            "result_sha256": digest,
            "binding_sha256": digest,
        },
        "completion_verifier": {
            "verifier": "control-plane/home",
            "independent": True,
            "verdict": "passed",
            "checks": {"result": True, "binding": True, "fencing_token": True},
        },
    }


def test_campaign_proof_accepts_only_fenced_content_bound_completion():
    module = load_module()
    assert module.proof_failures(verified_task(), "worker") == []


def test_campaign_proof_rejects_legacy_completed_without_verifier():
    module = load_module()
    task = verified_task()
    task["fencing_token"] = None
    task["completion_evidence"] = None
    task["completion_verifier"] = None

    failures = module.proof_failures(task, "worker")

    assert "fencing_token" in failures
    assert "evidence" in failures
    assert "verifier" in failures
