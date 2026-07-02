import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_paid_client_pipeline_is_draft_only_and_secret_safe():
    pipeline_mod = load_module(ROOT / "ops" / "paid_client_work.py")
    pipeline = pipeline_mod.build_pipeline(
        {
            "task_id": "KWORK-1",
            "client_alias": "Acme Client",
            "request_summary": "Build checkout fix with api_key=secret-value and ghp_1234567890abcdef",
            "repo_slug": "kolibri-ai-platform",
            "quote_basis": "Fixed scope after review",
            "deliverables": ["patch", "tests", "summary"],
        }
    )
    pipeline_mod.assert_safe_pipeline(pipeline)

    serialized = json.dumps(pipeline, ensure_ascii=False)
    assert "secret-value" not in serialized
    assert "ghp_1234567890abcdef" not in serialized
    assert pipeline["quote"]["send_to_client"] is False
    assert pipeline["quote"]["money_action_allowed"] is False
    assert pipeline["client_chat"]["send_to_client"] is False
    assert pipeline["branch"]["name"] == "client-work/acme-client/build-checkout-fix-with-api_key-redacted-and-github-token-redacted"
    assert {task["kind"] for task in pipeline["tasks"]} == {
        "paid_client_intake",
        "paid_client_quote_draft",
        "owner_remote_task",
        "paid_client_deliverable_pack",
    }
    for task in pipeline["tasks"]:
        assert task["public_action_allowed"] is False
        assert task["money_action_allowed"] is False
        assert "client_chat_safety_rules" in task["constraints"]


def test_control_plane_client_work_response_requires_owner_gate_for_task_creation(monkeypatch):
    control = load_module(ROOT / "ops" / "factory_control.py")
    created = []

    def fake_create_task(envelope):
        task = {"task_id": envelope["task_id"], "state": "queued", "envelope": envelope}
        created.append(task)
        return task

    monkeypatch.setattr(control, "create_task", fake_create_task)
    base_request = {
        "task_id": "KWORK-GATED",
        "client_alias": "Safe Client",
        "request_summary": "Create a product workflow",
        "repo_slug": "kolibri-ai-platform",
    }

    blocked = control.client_work_pipeline_response(base_request)
    assert blocked["status"] == "blocked"
    assert blocked["data"]["task_creation"]["created"] is False
    assert created == []

    approved = control.client_work_pipeline_response(base_request | {"owner_approved_for_internal_tasks": True})
    assert approved["status"] == "running"
    assert approved["data"]["task_creation"]["created"] is True
    assert approved["data"]["task_creation"]["created_task_ids"] == [
        "KWORK-GATED-INTAKE",
        "KWORK-GATED-QUOTE",
        "KWORK-GATED-IMPLEMENT",
        "KWORK-GATED-DELIVER",
    ]
    assert len(created) == 4


def test_dispatcher_exposes_paid_client_work_commands():
    dispatch = (ROOT / "ops" / "kolibri-dispatch").read_text(encoding="utf-8")
    assert '"client-work-plan"' in dispatch
    assert '"client-work-create"' in dispatch
    assert "--approve-internal-tasks" in dispatch
