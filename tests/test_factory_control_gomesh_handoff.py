import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_control():
    spec = importlib.util.spec_from_file_location("factory_control", ROOT / "ops" / "factory_control.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_gomesh_dev_handoff_requires_branch_and_objective():
    control = load_control()
    try:
        control.gomesh_dev_handoff_envelope({"objective": "Build GoMesh app task"})
    except ValueError as exc:
        assert "branch is required" in str(exc)
    else:
        raise AssertionError("expected branch validation")

    try:
        control.gomesh_dev_handoff_envelope({"branch": "agent/gomesh-app"})
    except ValueError as exc:
        assert "objective is required" in str(exc)
    else:
        raise AssertionError("expected objective validation")


def test_gomesh_dev_handoff_embeds_owner_rules_artifacts_and_completion_gate():
    control = load_control()
    envelope = control.gomesh_dev_handoff_envelope(
        {
            "task_id": "P0_PRODUCT_GOMESH_APP_DEV_AGENT_HANDOFF_PR_2026_07_02",
            "objective": "Continue concrete GoMesh app development work, not status-only reporting.",
            "branch": "agent/P0_PRODUCT_GOMESH_APP_DEV_AGENT_HANDOFF_PR_2026_07_02/generic",
            "active_agent": {
                "node": "mesh-agent-22",
                "cwd": "/var/lib/kolibri-agent/worktrees/gomesh/repo",
                "branch": "agent/P0_PRODUCT_GOMESH_APP_DEV_AGENT_HANDOFF_PR_2026_07_02/generic",
            },
        }
    )

    assert envelope["kind"] == "owner_remote_task"
    assert envelope["runner"] == "codex"
    assert envelope["target_node"] == "mesh-agent-22"
    assert envelope["required_capability"] == "generic_implementation"
    assert envelope["owner_rules"]["status_only_result_is_failure"] is True
    assert envelope["owner_rules"]["expected_output"] == "pushed_pr_branch_with_tests"
    assert envelope["constraints"]["push_to_main_forbidden"] is True
    assert envelope["constraints"]["force_push_forbidden"] is True
    assert envelope["constraints"]["artifact_discipline_required"] is True
    assert envelope["completion_gate"]["status_only_reports_rejected"] is True
    assert "what_now_works_for_owner" in envelope["required_result_fields"]
    assert control.GOMESH_DEV_REQUIRED_ARTIFACTS == envelope["required_artifacts"]
    assert "tests/test_factory_control_gomesh_handoff.py" in " ".join(envelope["verification_commands"])
    assert "TOKEN" not in str(envelope)
    assert "SECRET" not in str(envelope)


def test_gomesh_dev_handoff_rejects_unknown_expected_output():
    control = load_control()
    try:
        control.gomesh_dev_handoff_envelope(
            {
                "objective": "Build GoMesh app task",
                "branch": "agent/gomesh-app",
                "expected_output": "status_report_only",
            }
        )
    except ValueError as exc:
        assert "expected_output" in str(exc)
    else:
        raise AssertionError("expected output gate validation")
