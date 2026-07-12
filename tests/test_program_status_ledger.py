from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATUS_PATH = ROOT / "release" / "program-status.json"
DOC_PATH = ROOT / "docs" / "PROGRAM_STATUS.md"
ALLOWED_STATUSES = {"completed", "in_progress", "not_started", "blocked"}
SOURCE_COMMIT = "ca5e3a096ee390cd3d30e90ed7a6dd3e6639d872"
BUNDLE_DIGEST = "sha256:de00339d64be94772896e956a8bc3e05d125b6db0677285dc6835f2884baa56c"
CAMPAIGN_ID = "factory-ca5e3a09-final-20260713"


def load_status() -> dict:
    return json.loads(STATUS_PATH.read_text(encoding="utf-8"))


def assert_utc_timestamp(value: str) -> None:
    assert value.endswith("Z")
    datetime.fromisoformat(value.replace("Z", "+00:00"))


def walk_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_keys(child)


def test_program_status_schema_and_truth_invariants():
    status = load_status()

    assert status["schema_version"] == "kolibri.program-status.v1"
    assert status["program_id"] == "kolibri-ai-os-home-first"
    assert status["source_commit"] == SOURCE_COMMIT
    assert status["overall_status"] in ALLOWED_STATUSES
    assert_utc_timestamp(status["as_of"])
    assert set(status["truth_policy"]["allowed_gate_statuses"]) == ALLOWED_STATUSES
    assert status["truth_policy"]["unknown_is_not_zero"] is True
    assert status["truth_policy"]["heartbeat_is_not_execution_proof"] is True
    assert all("percent" not in key.lower() for key in walk_keys(status))
    assert "%" not in STATUS_PATH.read_text(encoding="utf-8")

    evidence_ids = [item["id"] for item in status["evidence"]]
    assert len(evidence_ids) == len(set(evidence_ids))
    for item in status["evidence"]:
        assert item["status"] in {"verified", "partial"}
        assert item["reference"]
        assert_utc_timestamp(item["observed_at"])

    gates = status["gates"]
    assert [gate["gate"] for gate in gates] == list(range(11))
    assert [gate["id"] for gate in gates] == [f"gate-{number}" for number in range(11)]
    for gate in gates:
        assert gate["status"] in ALLOWED_STATUSES
        assert gate["name"]
        assert gate["next_action"].strip()
        assert_utc_timestamp(gate["updated_at"])
        assert set(gate["evidence_ids"]).issubset(evidence_ids)


def test_program_status_records_only_current_proven_summary():
    status = load_status()
    summary = status["summary"]

    assert summary["ci"] == {"status": "green", "commit": SOURCE_COMMIT}
    assert summary["home_control_plane"]["status"] == "healthy"
    assert summary["runtime_bundle"]["digest"] == BUNDLE_DIGEST
    assert summary["fleet_proof"] == {
        "campaign_id": CAMPAIGN_ID,
        "status": "completed",
        "canonical_total": 21,
        "verified_total": 21,
        "failed_total": 0,
    }
    assert summary["development_seed"] == {
        "status": "blocked",
        "canonical_total": 20,
        "verified_total": 15,
        "lease_expired_total": 4,
        "runner_policy_blocked_total": 1,
        "lease_expired_cause": "fail_runner_binding",
    }
    assert summary["not_ready"] == [
        "portal",
        "shell",
        "improvement_controller",
        "rust_authority",
    ]

    assert status["gates"][4]["status"] == "completed"
    assert status["gates"][5]["status"] == "blocked"
    assert status["gates"][8]["status"] == "blocked"
    assert status["gates"][10]["status"] == "blocked"


def test_markdown_owner_view_matches_machine_ledger():
    document = DOC_PATH.read_text(encoding="utf-8")

    assert SOURCE_COMMIT in document
    assert BUNDLE_DIGEST in document
    assert CAMPAIGN_ID in document
    assert "15 of 20 verified" in document
    assert "four `lease_expired`" in document
    assert "one `runner_policy_blocked`" in document
    assert "does not report a completion percentage" in document
    for gate in range(11):
        assert f"| {gate} |" in document
