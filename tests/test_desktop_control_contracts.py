import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_contracts():
    path = ROOT / "backend" / "desktop_control_contracts.py"
    spec = importlib.util.spec_from_file_location("desktop_control_contracts", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_owner_contract_exposes_mvp_control_plane_endpoints():
    contracts = load_contracts()

    assert contracts.endpoint_pairs(contracts.OWNER_CONTROL_PLANE_ENDPOINTS) == {
        ("GET", "/health"),
        ("GET", "/v1/health"),
        ("GET", "/v1/nodes"),
        ("POST", "/v1/nodes/<node_id>/drain"),
        ("GET", "/v1/tasks?summary=1&compact=1"),
        ("GET", "/v1/tasks?state=<state>&limit=<n>"),
        ("GET", "/v1/tasks/<task_id>"),
        ("POST", "/v1/tasks"),
        ("POST", "/v1/tasks/<task_id>/cancel"),
        ("POST", "/v1/tasks/<task_id>/annotate"),
        ("GET", "/v1/agent-messages?target=all&limit=<n>"),
        ("POST", "/v1/agent-messages"),
    }


def test_destructive_owner_actions_require_confirmation():
    contracts = load_contracts()

    destructive = {
        endpoint.path
        for endpoint in contracts.OWNER_CONTROL_PLANE_ENDPOINTS
        if endpoint.requires_confirmation
    }

    assert "/v1/tasks" in destructive
    assert "/v1/tasks/<task_id>/cancel" in destructive
    assert "/v1/nodes/<node_id>/drain" in destructive


def test_worker_only_endpoints_are_not_owner_actions():
    contracts = load_contracts()

    owner_paths = {endpoint.path for endpoint in contracts.OWNER_CONTROL_PLANE_ENDPOINTS}
    worker_paths = {endpoint.path for endpoint in contracts.WORKER_ONLY_ENDPOINTS}

    assert not owner_paths.intersection(worker_paths)
    assert all(not endpoint.owner_action for endpoint in contracts.WORKER_ONLY_ENDPOINTS)


def test_current_desktop_control_envelope_matches_required_fields():
    contracts = load_contracts()
    envelope = json.loads(
        (ROOT / "ops" / "envelopes" / "KOL-DESKTOP-CONTROL-APP-MVP-20260629.json").read_text(encoding="utf-8")
    )

    assert contracts.validate_desktop_envelope(envelope) == []
    assert contracts.permission_pack_warnings(envelope) == [
        "permission_pack=full_autonomy requires explicit owner confirmation"
    ]


def test_envelope_validation_rejects_missing_required_fields_and_secret_markers():
    contracts = load_contracts()

    missing_errors = contracts.validate_desktop_envelope(
        {
            "task_id": "KOL-TEST",
            "kind": "generic_implementation",
            "goal": "write notes",
            "acceptance": ["done"],
        }
    )
    invalid_errors = contracts.validate_desktop_envelope(
        {
            "task_id": "KOL-TEST",
            "kind": "generic_implementation",
            "goal": "read /Users/name/.env",
            "acceptance": "done",
            "source": "manual",
        }
    )

    assert "missing required field: source" in missing_errors
    assert "acceptance must be a list" in invalid_errors
    assert "source must be an object" in invalid_errors
    assert "secret marker is not allowed in envelope: .env" in invalid_errors


def test_owner_summary_redacts_tokens_and_local_paths():
    contracts = load_contracts()

    summary = contracts.sanitize_owner_summary(
        "github_token=ghp_example123 log=/Users/kolibri/project/.env auth=/opt/kolibri-ai/data/auth.json"
    )

    assert "ghp_example123" not in summary
    assert "/Users/kolibri" not in summary
    assert "/opt/kolibri-ai" not in summary
    assert "[REDACTED]" in summary
    assert "[LOCAL_PATH_REDACTED]" in summary
