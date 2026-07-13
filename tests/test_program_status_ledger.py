from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATUS_PATH = ROOT / "release" / "program-status.json"
DOC_PATH = ROOT / "docs" / "PROGRAM_STATUS.md"
ALLOWED_STATUSES = {"completed", "in_progress", "not_started", "blocked"}
SOURCE_COMMIT = "c0f6c807617585ceb155d000d51d4c06d82883e4"
HOME_INTEGRATION_COMMIT = "7fc3ff6a24266caa204db02e8c4f05f4a4a2bbde"
CI_RUN_ID = 29214360515
BUNDLE_DIGEST = "sha256:de00339d64be94772896e956a8bc3e05d125b6db0677285dc6835f2884baa56c"
CAMPAIGN_ID = "factory-ca5e3a09-final-20260713"
RETRY_SNAPSHOT = "sha256:df090eab9ecc4956d60f1a01fbf70d79ac702f4e8100997e5054f525591d951b"
RETRY_PREFIX = "KOL-IMPROVE-SEED-r2-3b01332c"


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
    gate_progress = status["summary"]["acceptance_gate_progress"]
    assert gate_progress == {
        "completed": 2,
        "in_progress": 3,
        "blocked": 3,
        "not_started": 3,
        "total": 11,
        "completed_ratio": 0.1818,
        "interpretation": (
            "Equal gate-count ratio only; gates have unequal scope and this is not an effort estimate."
        ),
    }

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

    assert summary["ci"] == {
        "status": "green",
        "run_id": CI_RUN_ID,
        "commit": SOURCE_COMMIT,
        "jobs": {
            "ci": "success",
            "rust-1.97": "success",
            "kolibri-shell": "success",
        },
        "historical_red": {
            "commits": [
                "76e5d65e63eba2e5fcebe9dd93aef75857480594",
                "3b01332c67db970cf054bb3331b5c76c20ddee11",
            ],
            "cause": "python_3_14_timeout_classification_race",
        },
    }
    assert summary["home_development_environment"] == {
        "integration_worktree": {
            "status": "clean",
            "commit": HOME_INTEGRATION_COMMIT,
            "update_method": "fast_forward",
            "source_update_pending": SOURCE_COMMIT,
        },
        "codex_cli_version": "0.144.1",
        "canonical_manifest_readable": True,
        "linger": "yes",
        "root_helper": "installed_validated",
        "sudoers": "installed_validated",
    }
    assert summary["home_codex_provider"] == {
        "code_status": "committed_ci_green",
        "broker_service_activated": False,
        "provider_canary_completed": False,
        "credential_migration": {
            "status": "completed",
            "initial_apply": {
                "status": "failed",
                "root_state_unchanged": True,
                "reason": "existing_global_binding",
                "existing_binding": {
                    "node_id": "mac-codex-provider",
                    "credential_id": "mac-codex-provider-v1",
                    "epoch": 1,
                },
            },
            "current_binding": {
                "node_id": "home-codex-provider",
                "credential_id": "home-codex-provider-v2",
                "epoch": 2,
            },
            "owner_record_mode": "0600",
            "root_record_mode": "0600",
            "secrets_returned": False,
            "actors": {
                "mac-codex-provider": "drained",
                "home-codex-provider": "drained",
            },
        },
        "dry_run_status": "blocked",
        "dry_run_blocker": "current_user_codex_session_unavailable",
        "activation_blockers": ["current_user_codex_session_unavailable"],
        "official_device_login": {
            "status": "waiting_for_owner_unlock",
            "mac_screen_locked": True,
        },
        "activation_sequence": [
            "unlock_mac",
            "complete_device_login",
            "install_and_start",
            "readiness",
            "fenced_canary",
            "undrain",
        ],
        "status": "blocked",
    }
    assert summary["home_control_plane"]["status"] == "healthy"
    assert summary["runtime_bundle"]["digest"] == BUNDLE_DIGEST
    assert summary["fleet_proof"] == {
        "campaign_id": CAMPAIGN_ID,
        "status": "completed",
        "canonical_total": 21,
        "verified_total": 21,
        "failed_total": 0,
    }
    development_seed = summary["development_seed"]
    assert development_seed["status"] == "blocked"
    assert development_seed["canonical_total"] == 20
    assert development_seed["previously_verified_total"] == 15
    retry = development_seed["retry"]
    assert retry["snapshot_digest"] == RETRY_SNAPSHOT
    assert retry["task_prefix"] == RETRY_PREFIX
    assert retry["target_total"] == retry["terminal_total"] == 5
    assert retry["completed_total"] == 0
    assert retry["result_hash_total"] == 0
    assert retry["truth_verified_total"] == 0
    assert retry["binding"] == {
        "status": "verified",
        "verified_total": 5,
        "leases_cleared_total": 5,
    }
    assert retry["failures"] == [
        {
            "count": 4,
            "state": "mimo_session_not_found",
            "terminal_attempt": 2,
            "max_attempts": 2,
            "terminal_cause": "mimo_session_not_found",
            "classification_fix": "implemented_and_locally_verified",
        },
        {
            "count": 1,
            "node_id": "qjns",
            "state": "runner_policy_blocked",
            "attempt": 1,
            "max_attempts": 2,
            "terminal_cause": "illegal_access",
        },
    ]
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
    assert "15 of 20 were previously verified" in document
    assert RETRY_SNAPSHOT in document
    assert RETRY_PREFIX in document
    assert str(CI_RUN_ID) in document
    assert "`ci`, `rust-1.97`, and `kolibri-shell` all succeeded" in document
    assert "Codex CLI upgraded to `0.144.1`" in document
    assert "current_user_codex_session_unavailable" in document
    assert "official device login is waiting for owner unlock" in document
    assert "service is not activated, no provider canary exists" in document
    assert "home-codex-provider-v2`" in document
    assert "epoch 2" in document
    assert "`secrets_returned=false`" in document
    assert "Active with `NRestarts=0`" in document
    assert "root helper and sudoers are installed and validated" in document
    assert "Credential migration and drained actor provisioning are complete" in document
    assert "The only current Codex activation blocker is `current_user_codex_session_unavailable`" in document
    assert "provision the drained actor" not in document
    assert "5 of 5 terminal failed" in document
    assert "bindings are verified and leases are cleared" in document
    assert "Mimo returned `Session not found`" in document
    assert "`runner_policy_blocked` for `illegal_access` at attempt 1 of 2" in document
    assert "Python 3.14 timeout-classification race" in document
    assert "Completed: `2/11` gates (`18.2%` by equal gate count)" in document
    assert "product release is not ready" in document
    for gate in range(11):
        assert f"| {gate} |" in document
