"""Tests for Telegram HA failover guard."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import importlib.util
import sys

ROOT = Path(__file__).resolve().parents[1]


def load_guard():
    spec = importlib.util.spec_from_file_location(
        "telegram_failover_guard", ROOT / "ops" / "telegram_failover_guard.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_compute_state_hash_deterministic():
    guard = load_guard()
    data = {"offset": 10, "tracked": {"T1": {"chat_id": 100}}}
    h1 = guard.compute_state_hash(data)
    h2 = guard.compute_state_hash(data)
    assert h1 == h2
    assert len(h1) == 64


def test_compute_state_hash_excludes_keys():
    guard = load_guard()
    data = {"offset": 10, "owner_chat_id": 100, "tracked": {}}
    h1 = guard.compute_state_hash(data, frozenset({"owner_chat_id"}))
    h2 = guard.compute_state_hash(data, frozenset())
    assert h1 != h2


def test_load_failover_state_returns_defaults_when_missing(tmp_path):
    guard = load_guard()
    state = guard.load_failover_state(tmp_path / "missing.json")
    assert state.primary_healthy is True
    assert state.promotion_blocked is False
    assert state.dual_receiver_detected is False


def test_load_failover_state_roundtrip(tmp_path):
    guard = load_guard()
    state = guard.FailoverState(
        primary_gateway_id="primary-gw",
        primary_healthy=False,
        last_promotion_attempt=1000.0,
        state_hash="abc123",
    )
    path = tmp_path / "failover.json"
    guard.save_failover_state(state, path)
    loaded = guard.load_failover_state(path)
    assert loaded.primary_gateway_id == "primary-gw"
    assert loaded.primary_healthy is False
    assert loaded.last_promotion_attempt == 1000.0
    assert loaded.state_hash == "abc123"


def test_save_failover_state_creates_parent_dirs(tmp_path):
    guard = load_guard()
    path = tmp_path / "nested" / "dir" / "state.json"
    guard.save_failover_state(guard.FailoverState(), path)
    assert path.exists()


def test_detect_dual_receiver_single_primary():
    guard = load_guard()
    result = guard.detect_dual_receiver(primary_polling=True, standby_polling=False, webhook_active=False)
    assert result["ok"] is True
    assert result["active_count"] == 1
    assert result["violations"] == []


def test_detect_dual_receiver_violation():
    guard = load_guard()
    result = guard.detect_dual_receiver(primary_polling=True, standby_polling=True, webhook_active=False)
    assert result["ok"] is False
    assert result["active_count"] == 2
    assert len(result["violations"]) == 1
    assert result["violations"][0]["type"] == "dual_receiver"
    assert "primary-polling" in result["violations"][0]["receivers"]
    assert "standby-polling" in result["violations"][0]["receivers"]


def test_detect_dual_receiver_all_active():
    guard = load_guard()
    result = guard.detect_dual_receiver(primary_polling=True, standby_polling=True, webhook_active=True)
    assert result["ok"] is False
    assert result["active_count"] == 3


def test_detect_dual_receiver_none_active():
    guard = load_guard()
    result = guard.detect_dual_receiver(primary_polling=False, standby_polling=False, webhook_active=False)
    assert result["ok"] is True
    assert result["active_count"] == 0


def test_verify_state_replication_match(tmp_path):
    guard = load_guard()
    state_data = {"offset": 10, "tracked": {"T1": {"chat_id": 100}}}
    (tmp_path / "primary.json").write_text(json.dumps(state_data))
    (tmp_path / "standby.json").write_text(json.dumps(state_data))
    result = guard.verify_state_replication(tmp_path / "primary.json", tmp_path / "standby.json")
    assert result["ok"] is True
    assert result["match"] is True


def test_verify_state_replication_mismatch(tmp_path):
    guard = load_guard()
    (tmp_path / "primary.json").write_text(json.dumps({"tracked": {"T1": {"chat_id": 100}}}))
    (tmp_path / "standby.json").write_text(json.dumps({"tracked": {"T1": {"chat_id": 200}}}))
    result = guard.verify_state_replication(tmp_path / "primary.json", tmp_path / "standby.json")
    assert result["ok"] is False
    assert result["match"] is False


def test_verify_state_replication_missing_primary(tmp_path):
    guard = load_guard()
    result = guard.verify_state_replication(tmp_path / "missing.json", tmp_path / "also-missing.json")
    assert result["ok"] is False
    assert result["error"] == "primary_state_missing"


def test_verify_state_replication_missing_standby(tmp_path):
    guard = load_guard()
    (tmp_path / "primary.json").write_text(json.dumps({"offset": 10}))
    result = guard.verify_state_replication(tmp_path / "primary.json", tmp_path / "missing.json")
    assert result["ok"] is False
    assert result["error"] == "standby_state_missing"


def test_verify_state_replication_excludes_owner_chat_id(tmp_path):
    guard = load_guard()
    p = {"offset": 10, "owner_chat_id": 100, "tracked": {}}
    s = {"offset": 10, "owner_chat_id": 200, "tracked": {}}
    (tmp_path / "primary.json").write_text(json.dumps(p))
    (tmp_path / "standby.json").write_text(json.dumps(s))
    result = guard.verify_state_replication(tmp_path / "primary.json", tmp_path / "standby.json")
    assert result["ok"] is True


def test_check_primary_health_online_fresh():
    guard = load_guard()
    result = guard.check_primary_health(health_data={
        "health": "online",
        "heartbeat_at": str(time.time()),
    })
    assert result["ok"] is True
    assert result["is_online"] is True
    assert result["heartbeat_fresh"] is True


def test_check_primary_health_stale_heartbeat():
    guard = load_guard()
    result = guard.check_primary_health(health_data={
        "health": "online",
        "heartbeat_at": str(time.time() - 300),
    })
    assert result["ok"] is False
    assert result["heartbeat_fresh"] is False


def test_check_primary_health_offline():
    guard = load_guard()
    result = guard.check_primary_health(health_data={
        "health": "offline",
        "heartbeat_at": str(time.time()),
    })
    assert result["ok"] is False
    assert result["is_online"] is False


def test_check_primary_health_no_heartbeat():
    guard = load_guard()
    result = guard.check_primary_health(health_data={"health": "online"})
    assert result["ok"] is False
    assert result["heartbeat_fresh"] is False


def test_evaluate_failover_promotion_primary_healthy():
    guard = load_guard()
    state = guard.FailoverState(replication_verified=True)
    health = {"ok": True}
    result = guard.evaluate_failover_promotion(state, health)
    assert result["should_promote"] is False
    assert result["reason"] == "primary_healthy"


def test_evaluate_failover_promotion_blocked():
    guard = load_guard()
    state = guard.FailoverState(promotion_blocked=True, replication_verified=True)
    health = {"ok": False}
    result = guard.evaluate_failover_promotion(state, health)
    assert result["should_promote"] is False
    assert result["reason"] == "promotion_blocked"


def test_evaluate_failover_promotion_cooldown_active():
    guard = load_guard()
    state = guard.FailoverState(
        last_promotion_attempt=time.time() - 60,
        replication_verified=True,
    )
    health = {"ok": False}
    result = guard.evaluate_failover_promotion(state, health)
    assert result["should_promote"] is False
    assert result["reason"] == "cooldown_active"
    assert "cooldown_remaining_seconds" in result


def test_evaluate_failover_promotion_replication_not_verified():
    guard = load_guard()
    state = guard.FailoverState(replication_verified=False)
    health = {"ok": False}
    result = guard.evaluate_failover_promotion(state, health)
    assert result["should_promote"] is False
    assert result["reason"] == "replication_not_verified"


def test_evaluate_failover_promotion_eligible():
    guard = load_guard()
    state = guard.FailoverState(
        last_promotion_attempt=time.time() - 400,
        replication_verified=True,
    )
    health = {"ok": False}
    result = guard.evaluate_failover_promotion(state, health, now=time.time())
    assert result["should_promote"] is True
    assert result["reason"] == "primary_unhealthy_cooldown_passed"


def test_standby_mode_disabled_while_primary_healthy():
    guard = load_guard()
    result = guard.standby_gateway_mode(
        is_primary_healthy=True,
        is_active_receiver=True,
        webhook_configured=False,
    )
    assert result["mode"] == "disabled"
    assert result["can_process_updates"] is False


def test_standby_mode_send_only_primary_healthy():
    guard = load_guard()
    result = guard.standby_gateway_mode(
        is_primary_healthy=True,
        is_active_receiver=False,
        webhook_configured=False,
    )
    assert result["mode"] == "send-only"
    assert result["can_process_updates"] is False


def test_standby_mode_active_primary_unhealthy():
    guard = load_guard()
    result = guard.standby_gateway_mode(
        is_primary_healthy=False,
        is_active_receiver=False,
        webhook_configured=False,
    )
    assert result["mode"] == "active"
    assert result["can_process_updates"] is True


def test_standby_mode_send_only_webhook_active():
    guard = load_guard()
    result = guard.standby_gateway_mode(
        is_primary_healthy=False,
        is_active_receiver=False,
        webhook_configured=True,
    )
    assert result["mode"] == "send-only"
    assert result["can_process_updates"] is False


def test_validate_gateway_startup_standby_polling_while_primary_healthy():
    guard = load_guard()
    result = guard.validate_gateway_startup(
        role="standby",
        update_receiver="polling",
        webhook_url=None,
        primary_healthy=True,
    )
    assert result["ok"] is False
    assert len(result["violations"]) == 1
    assert result["violations"][0]["type"] == "standby_polling_while_primary_healthy"


def test_validate_gateway_startup_primary_polling_ok():
    guard = load_guard()
    result = guard.validate_gateway_startup(
        role="primary",
        update_receiver="polling",
        webhook_url=None,
    )
    assert result["ok"] is True
    assert result["violations"] == []


def test_validate_gateway_startup_standby_disabled_ok():
    guard = load_guard()
    result = guard.validate_gateway_startup(
        role="standby",
        update_receiver="disabled",
        webhook_url=None,
        primary_healthy=True,
    )
    assert result["ok"] is True


def test_record_and_read_heartbeat(tmp_path):
    guard = load_guard()
    state_path = tmp_path / "state.json"
    state_path.write_text("{}")
    guard.record_heartbeat("test-gw", state_path, now=1000.0)
    hb = guard.read_heartbeat("test-gw", state_path)
    assert hb["exists"] is True
    assert hb["heartbeat_at"] == 1000.0


def test_read_heartbeat_missing():
    guard = load_guard()
    state_path = Path("/nonexistent/state.json")
    hb = guard.read_heartbeat("missing-gw", state_path)
    assert hb["exists"] is False


def test_format_failover_status_no_secrets():
    guard = load_guard()
    state = guard.FailoverState(primary_healthy=True, replication_verified=True)
    health = {"ok": True, "message": "Primary is healthy"}
    text = guard.format_failover_status(state, health)
    assert "Primary healthy: True" in text
    assert "State replication verified: True" in text
    for secret in ["token", "secret", "key", "password"]:
        assert secret not in text.lower()


def test_gateway_role_can_poll_primary_active():
    guard = load_guard()
    role = guard.GatewayRole(
        role="primary", mode="active", is_active_receiver=True, health_ok=True
    )
    assert role.can_poll is True


def test_gateway_role_can_poll_standby():
    guard = load_guard()
    role = guard.GatewayRole(
        role="standby", mode="send-only", is_active_receiver=False, health_ok=True
    )
    assert role.can_poll is False


def test_gateway_role_should_promote_standby_healthy():
    guard = load_guard()
    role = guard.GatewayRole(
        role="standby", mode="send-only", is_active_receiver=False, health_ok=True
    )
    assert role.should_promote is True


def test_gateway_role_should_promote_primary():
    guard = load_guard()
    role = guard.GatewayRole(
        role="primary", mode="active", is_active_receiver=True, health_ok=True
    )
    assert role.should_promote is False
