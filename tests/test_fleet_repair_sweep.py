import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_sweep():
    spec = importlib.util.spec_from_file_location("fleet_repair_sweep", ROOT / "ops" / "fleet_repair_sweep.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_sweep_creates_api_unreachable_repair_envelope_for_ssh_failed_node():
    sweep = load_sweep()
    rows = sweep.parse_sweep_lines("hostvds-agent-10|ssh_failed\n")

    envelopes = sweep.build_repair_envelopes(
        rows,
        observed_at="2026-07-02T15:55:00+00:00",
        date_slug="2026_07_02",
    )

    assert len(envelopes) == 1
    envelope = envelopes[0]
    assert envelope["task_id"] == "P0_REPAIR_HOSTVDS_AGENT_10_API_UNREACHABLE_2026_07_02"
    assert envelope["kind"] == "owner_remote_task"
    assert envelope["target_node"] == "main"
    assert envelope["branch"] == "codex/p0-repair-hostvds-agent-10-api-unreachable-2026-07-02"
    assert envelope["base_ref"] == "main"
    assert envelope["write_scope"] == [
        "docs/agent/runs/2026-07-02-p0-repair-hostvds-agent-10-api-unreachable-2026-07-02/**",
        "docs/ops/hostvds/**",
    ]
    assert envelope["verification_commands"] == ["test -s RESULT.md", "test -s NEXT.md"]
    assert envelope["blocked_status"] == {
        "status": "blocked",
        "node": "hostvds-agent-10",
        "target_node": "hostvds-agent-10",
        "reason": "api_unreachable",
        "condition": "ssh_failed",
        "fallback_nodes": ["main", "server-kfrm", "kolibri-9fts", "kolibri-new", "kolibri-uiap", "kolibri-qjns"],
        "fallback_route": {"type": "fabric_api_relay", "endpoint": "/v1/fabric/relay"},
        "can_continue_elsewhere": True,
        "repair_task": "P0_REPAIR_HOSTVDS_AGENT_10_API_UNREACHABLE_2026_07_02",
        "next_action": "run read-only network, provider status, firewall, and Agent Host diagnostics through a reachable relay",
    }
    assert envelope["repair"]["server_name"] == "kolibri-hk-edge-load"
    assert envelope["repair"]["address"] == "217.60.38.191"
    assert envelope["constraints"]["no_paid_actions"] is True


def test_sweep_does_not_create_repair_for_healthy_node():
    sweep = load_sweep()
    rows = sweep.parse_sweep_lines(
        "hostvds-agent-01|ok|kolibri-backend-lead|repo=f7ac32c|mem=yes|pmem=yes|"
        "agent=active|sync=active|code=active|loopback=yes|http=401|public_mimo=no|agent_project_env=2\n"
    )

    assert sweep.build_repair_envelopes(rows, observed_at="2026-07-02T15:55:00+00:00") == []


def test_sweep_flags_public_mimo_listener_before_accepting_node():
    sweep = load_sweep()
    rows = sweep.parse_sweep_lines(
        "kolibri-uiap|ok|kolibri-rag-knowledge|repo=f7ac32c|mem=yes|pmem=yes|"
        "agent=active|sync=active|code=active|loopback=yes|http=401|public_mimo=yes|agent_project_env=2\n"
    )

    envelopes = sweep.build_repair_envelopes(rows, observed_at="2026-07-02T15:55:00+00:00")

    assert len(envelopes) == 1
    assert envelopes[0]["repair"]["kind"] == "repair_public_mimocode_listener"
    assert envelopes[0]["blocked_status"]["reason"] == "public_mimocode_listener"
