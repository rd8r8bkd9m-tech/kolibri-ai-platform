from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_home_screen(monkeypatch, tmp_path):
    fixture = tmp_path / "fixtures"
    fixture.mkdir()
    (fixture / "health.json").write_text(json.dumps({"status": "ok", "queue_backend": "redis"}), encoding="utf-8")
    (fixture / "nodes.json").write_text(
        json.dumps(
            {
                "nodes": [
                    {"node_id": "home", "status": "online", "freshness": "fresh", "agent_id": "agent-host-home", "capabilities": ["orchestrator"]},
                    {"node_id": "qjns", "status": "offline", "freshness": "stale", "agent_id": "agent-host-qjns", "capabilities": ["review"]},
                ]
            }
        ),
        encoding="utf-8",
    )
    (fixture / "tasks.json").write_text(
        json.dumps(
            {
                "tasks": [
                    {"task_id": "P0_PRODUCT_HOME_SCREEN_TMUX_UI_DEPLOY_2026_07_02", "state": "running", "lease_owner": "home:agent-host-home", "objective": "Deploy tmux"},
                    {"task_id": "P0_BLOCKED", "state": "queued", "lease_owner": None, "error_type": "blocked_secret token=should-not-render"},
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("KOLIBRI_HOME_SCREEN_FIXTURE_DIR", str(fixture))
    spec = importlib.util.spec_from_file_location("kolibri_home_screen", ROOT / "ops" / "kolibri_home_screen.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_home_screen_renders_required_russian_panes_without_secrets(monkeypatch, tmp_path):
    screen = load_home_screen(monkeypatch, tmp_path)
    for pane in ("overview", "tasks", "agents", "prs", "logs", "blockers", "owner"):
        output = screen.RENDERERS[pane]()
        assert screen.PANE_TITLES[pane] in output
        assert "should-not-render" not in output
    assert "Серверы" in screen.render_overview()
    assert "Задачи" in screen.render_overview()
    assert "ИНСТРУКЦИИ ВЛАДЕЛЬЦА" in screen.render_owner()


def test_tmux_plan_has_six_owner_visible_panes_and_auto_refresh(monkeypatch, tmp_path):
    screen = load_home_screen(monkeypatch, tmp_path)
    plan = "\n".join(" ".join(command) for command in screen.tmux_plan())
    assert "kolibri-factory-screen" in plan
    for pane in ("overview", "tasks", "agents", "prs", "logs", "blockers", "owner"):
        assert f"pane {pane}" in plan
    assert "while true" in plan
    assert "sleep 15" in plan


def test_systemd_unit_is_reversible_user_service_without_secret_env_file():
    unit = (ROOT / "ops" / "systemd" / "kolibri-home-screen.service").read_text(encoding="utf-8")
    assert "ExecStart=/bin/bash /opt/kolibri-ai-platform/ops/kolibri-home-screen start" in unit
    assert "ExecStop=/bin/bash /opt/kolibri-ai-platform/ops/kolibri-home-screen stop" in unit
    assert "EnvironmentFile=-%h/.config/kolibri/home-screen.env" in unit
    assert "TELEGRAM" not in unit
    assert "TOKEN" not in unit


def test_redaction_covers_common_secret_shapes(monkeypatch, tmp_path):
    screen = load_home_screen(monkeypatch, tmp_path)
    redacted = screen.redact("token=abc password:xyz Authorization Bearer-123 cookie=session")
    assert "abc" not in redacted
    assert "xyz" not in redacted
    assert "Bearer-123" not in redacted
    assert "session" not in redacted
    assert "<redacted>" in redacted
