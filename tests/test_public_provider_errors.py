from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from public_errors import (
    public_execution_failure,
    public_provider_failure,
    public_verification_failure,
)


def test_provider_timeout_is_truthful_aggregated_and_redacted():
    secret = "Bearer must-not-leak"
    failure = public_provider_failure({
        "error_type": "provider_timeout",
        "upstream_body": secret,
        "attempts": [
            {
                "provider": "private-mimo-route",
                "node_id": "private-node",
                "status": "failed",
                "error_type": "provider_timeout",
            },
            {
                "provider": "private-codex-route",
                "status": "cancelled",
                "error_type": "provider_timeout",
            },
        ],
    })

    assert failure == {
        "type": "provider_unavailable",
        "code": "provider_timeout",
        "message": "The configured model routes reached their execution deadline before one completed.",
        "retryable": True,
        "attempt_summary": {
            "attempted": 2,
            "failed": 1,
            "timed_out": 2,
            "cancelled": 1,
            "skipped": 0,
        },
    }
    assert secret not in str(failure)
    assert "private-mimo-route" not in str(failure)
    assert "private-node" not in str(failure)


def test_provider_failure_distinguishes_no_route_from_rejected_output():
    unavailable = public_provider_failure({"attempts": []})
    rejected = public_provider_failure({
        "error_type": "factory_evidence_invalid",
        "attempts": [{"status": "failed", "error_type": "factory_evidence_invalid"}],
    })

    assert unavailable["code"] == "provider_routes_unavailable"
    assert unavailable["attempt_summary"]["attempted"] == 0
    assert rejected["code"] == "provider_result_rejected"
    assert rejected["retryable"] is False


def test_unleased_route_is_reported_as_capacity_only_after_exhaustion():
    failure = public_provider_failure({
        "attempts": [
            {"status": "failed", "error_type": "factory_lease_unavailable"},
            {"status": "failed", "error_type": "factory_no_fresh_capable_worker"},
        ],
        "error_type": "factory_lease_unavailable",
    })

    assert failure["code"] == "provider_capacity_unavailable"
    assert failure["retryable"] is True
    assert failure["attempt_summary"]["attempted"] == 2


def test_verification_failure_does_not_use_the_forbidden_catch_all_copy():
    failure = public_verification_failure()

    assert failure["code"] == "verification_failed"
    assert "could not produce a verified" not in failure["message"].lower()


def test_forbidden_catch_all_is_absent_from_public_runtime_sources():
    forbidden = " ".join(("Kolibri could not produce", "a verified response")).lower()
    sources = [
        BACKEND / "execution_api.py",
        BACKEND / "public_responses_api.py",
        BACKEND / "public_errors.py",
        ROOT / "frontend" / "src" / "runtime" / "kolibriApi.js",
    ]

    assert all(forbidden not in path.read_text(encoding="utf-8").lower() for path in sources)


def test_internal_execution_failure_is_not_mislabeled_as_provider_exhaustion():
    failure = public_execution_failure()

    assert failure["code"] == "response_internal_error"
    assert failure["type"] == "response_internal_error"
    assert "provider" not in failure["message"].lower()
