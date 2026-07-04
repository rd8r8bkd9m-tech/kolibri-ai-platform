#!/usr/bin/env python3
"""Failover guard for Telegram bot HA with active/standby gateway roles.

This module enforces:
- Single active Telegram update receiver (no dual polling)
- Standby gateway detection and prevention of update processing
- State hash verification for standby replication
- Primary health check gating for failover promotion

The guard is intentionally standard-library-only for zero runtime dependencies.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any


GATEWAY_ROLE_PRIMARY = "primary"
GATEWAY_ROLE_STANDBY = "standby"
GATEWAY_ROLE_DISABLED = "disabled"

GATEWAY_MODES = {"active", "send-only", "disabled"}

HEALTH_CHECK_TIMEOUT_SECONDS = 10
FAILOVER_PROMOTION_COOLDOWN_SECONDS = 300

TOKEN_LIKE_RE = re.compile(
    r"(?i)(?:\b\d{6,}:[A-Za-z0-9_-]{20,}\b|\b(?:ghp|github_pat|xox[baprs]|sk)-[A-Za-z0-9_-]{16,}\b|\b[A-Fa-f0-9]{40,}\b)"
)


def _redact_secrets(text: str) -> str:
    return TOKEN_LIKE_RE.sub("[REDACTED]", text)


class GatewayRole:
    """Represents the runtime role of a Telegram gateway instance."""

    def __init__(
        self,
        role: str,
        mode: str,
        is_active_receiver: bool,
        health_ok: bool,
        state_hash: str | None = None,
        last_heartbeat: float | None = None,
        details: dict[str, Any] | None = None,
    ):
        self.role = role
        self.mode = mode
        self.is_active_receiver = is_active_receiver
        self.health_ok = health_ok
        self.state_hash = state_hash
        self.last_heartbeat = last_heartbeat
        self.details = details or {}

    @property
    def can_poll(self) -> bool:
        return self.role == GATEWAY_ROLE_PRIMARY and self.mode == "active" and self.is_active_receiver

    @property
    def should_promote(self) -> bool:
        return (
            self.role == GATEWAY_ROLE_STANDBY
            and self.health_ok
            and self.mode != "disabled"
        )


class FailoverState:
    """Persistent failover state stored on disk."""

    def __init__(
        self,
        primary_gateway_id: str | None = None,
        standby_gateway_id: str | None = None,
        primary_healthy: bool = True,
        last_health_check: float = 0.0,
        last_promotion_attempt: float = 0.0,
        promotion_blocked: bool = False,
        state_hash: str | None = None,
        replication_verified: bool = False,
        dual_receiver_detected: bool = False,
    ):
        self.primary_gateway_id = primary_gateway_id
        self.standby_gateway_id = standby_gateway_id
        self.primary_healthy = primary_healthy
        self.last_health_check = last_health_check
        self.last_promotion_attempt = last_promotion_attempt
        self.promotion_blocked = promotion_blocked
        self.state_hash = state_hash
        self.replication_verified = replication_verified
        self.dual_receiver_detected = dual_receiver_detected


def compute_state_hash(state_data: dict[str, Any], exclude_keys: frozenset[str] | None = None) -> str:
    """Compute SHA-256 hash of state data for replication verification."""
    exclude = exclude_keys or frozenset()
    canonical = json.dumps(
        {k: v for k, v in sorted(state_data.items()) if k not in exclude},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_failover_state(path: Path) -> FailoverState:
    """Load failover state from disk."""
    if not path.exists():
        return FailoverState()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return FailoverState(
            primary_gateway_id=data.get("primary_gateway_id"),
            standby_gateway_id=data.get("standby_gateway_id"),
            primary_healthy=data.get("primary_healthy", True),
            last_health_check=data.get("last_health_check", 0.0),
            last_promotion_attempt=data.get("last_promotion_attempt", 0.0),
            promotion_blocked=data.get("promotion_blocked", False),
            state_hash=data.get("state_hash"),
            replication_verified=data.get("replication_verified", False),
            dual_receiver_detected=data.get("dual_receiver_detected", False),
        )
    except (json.JSONDecodeError, KeyError):
        return FailoverState()


def save_failover_state(state: FailoverState, path: Path) -> None:
    """Persist failover state to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "primary_gateway_id": state.primary_gateway_id,
        "standby_gateway_id": state.standby_gateway_id,
        "primary_healthy": state.primary_healthy,
        "last_health_check": state.last_health_check,
        "last_promotion_attempt": state.last_promotion_attempt,
        "promotion_blocked": state.promotion_blocked,
        "state_hash": state.state_hash,
        "replication_verified": state.replication_verified,
        "dual_receiver_detected": state.dual_receiver_detected,
    }
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def detect_dual_receiver(
    primary_polling: bool,
    standby_polling: bool,
    webhook_active: bool,
) -> dict[str, Any]:
    """Detect if multiple update receivers are active simultaneously.

    Returns detection result with violations list.
    """
    violations = []
    active_count = sum([primary_polling, standby_polling, webhook_active])

    if active_count > 1:
        receivers = []
        if primary_polling:
            receivers.append("primary-polling")
        if standby_polling:
            receivers.append("standby-polling")
        if webhook_active:
            receivers.append("webhook")
        violations.append({
            "type": "dual_receiver",
            "receivers": receivers,
            "active_count": active_count,
            "message": f"Multiple active receivers detected: {', '.join(receivers)}",
        })

    return {
        "ok": active_count <= 1,
        "active_count": active_count,
        "violations": violations,
    }


def verify_state_replication(
    primary_state_path: Path,
    standby_state_path: Path,
    exclude_keys: frozenset[str] | None = None,
) -> dict[str, Any]:
    """Verify standby state hash matches primary state.

    Compares the SHA-256 hash of relevant state fields between primary
    and standby to ensure replication consistency.
    """
    if not primary_state_path.exists():
        return {
            "ok": False,
            "error": "primary_state_missing",
            "message": "Primary state file not found",
        }

    if not standby_state_path.exists():
        return {
            "ok": False,
            "error": "standby_state_missing",
            "message": "Standby state file not found",
        }

    try:
        primary_data = json.loads(primary_state_path.read_text(encoding="utf-8"))
        standby_data = json.loads(standby_state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {
            "ok": False,
            "error": "state_read_error",
            "message": _redact_secrets(str(exc)),
        }

    exclude = exclude_keys or frozenset({"owner_chat_id", "offset"})
    primary_hash = compute_state_hash(primary_data, exclude)
    standby_hash = compute_state_hash(standby_data, exclude)

    return {
        "ok": primary_hash == standby_hash,
        "primary_hash": primary_hash[:16],
        "standby_hash": standby_hash[:16],
        "match": primary_hash == standby_hash,
        "message": (
            "State replication verified"
            if primary_hash == standby_hash
            else "State hash mismatch - replication may be stale"
        ),
    }


def check_primary_health(
    health_endpoint: str | None = None,
    health_data: dict[str, Any] | None = None,
    max_heartbeat_age_seconds: int = 120,
) -> dict[str, Any]:
    """Check if the primary gateway is healthy.

    Uses heartbeat freshness or HTTP health endpoint to determine
    if the primary is alive and should continue serving.
    """
    if health_data is None:
        health_data = {}

    heartbeat_at = health_data.get("heartbeat_at")
    health_status = health_data.get("health", "unknown")
    is_online = health_status == "online"

    if heartbeat_at:
        try:
            heartbeat_ts = float(heartbeat_at)
            age = time.time() - heartbeat_ts
            heartbeat_fresh = age < max_heartbeat_age_seconds
        except (ValueError, TypeError):
            heartbeat_fresh = False
            age = float("inf")
    else:
        heartbeat_fresh = False
        age = float("inf")

    healthy = is_online and heartbeat_fresh

    return {
        "ok": healthy,
        "health_status": health_status,
        "heartbeat_age_seconds": round(age, 1) if age != float("inf") else None,
        "heartbeat_fresh": heartbeat_fresh,
        "is_online": is_online,
        "message": (
            "Primary is healthy"
            if healthy
            else f"Primary unhealthy: status={health_status}, heartbeat_age={round(age, 1)}s"
        ),
    }


def evaluate_failover_promotion(
    failover_state: FailoverState,
    primary_health: dict[str, Any],
    now: float | None = None,
) -> dict[str, Any]:
    """Evaluate whether standby should be promoted to active.

    Checks:
    1. Primary is unhealthy
    2. Promotion cooldown has elapsed
    3. Promotion is not blocked
    4. Standby state is fresh
    """
    current_time = now if now is not None else time.time()

    if primary_health.get("ok"):
        return {
            "should_promote": False,
            "reason": "primary_healthy",
            "message": "Primary is healthy - no promotion needed",
        }

    if failover_state.promotion_blocked:
        return {
            "should_promote": False,
            "reason": "promotion_blocked",
            "message": "Failover promotion is blocked by operator",
        }

    cooldown_remaining = (
        failover_state.last_promotion_attempt + FAILOVER_PROMOTION_COOLDOWN_SECONDS
    ) - current_time
    if cooldown_remaining > 0:
        return {
            "should_promote": False,
            "reason": "cooldown_active",
            "cooldown_remaining_seconds": round(cooldown_remaining, 1),
            "message": f"Promotion cooldown active: {round(cooldown_remaining, 1)}s remaining",
        }

    if not failover_state.replication_verified:
        return {
            "should_promote": False,
            "reason": "replication_not_verified",
            "message": "State replication not verified - cannot promote",
        }

    return {
        "should_promote": True,
        "reason": "primary_unhealthy_cooldown_passed",
        "message": "Primary unhealthy and cooldown passed - promotion eligible",
    }


def standby_gateway_mode(
    is_primary_healthy: bool,
    is_active_receiver: bool,
    webhook_configured: bool,
) -> dict[str, Any]:
    """Determine the correct mode for a standby gateway.

    Returns the mode and whether the gateway should process updates.
    """
    if is_active_receiver and is_primary_healthy:
        return {
            "mode": "disabled",
            "can_process_updates": False,
            "reason": "standby_must_not_poll_while_primary_healthy",
            "message": "Standby cannot be active receiver while primary is healthy",
        }

    if webhook_configured:
        return {
            "mode": "send-only",
            "can_process_updates": False,
            "reason": "webhook_active",
            "message": "Webhook is active - standby operates in send-only mode",
        }

    if is_primary_healthy:
        return {
            "mode": "send-only",
            "can_process_updates": False,
            "reason": "primary_healthy",
            "message": "Primary is healthy - standby in send-only mode",
        }

    return {
        "mode": "active",
        "can_process_updates": True,
        "reason": "primary_unhealthy_promotion_eligible",
        "message": "Primary unhealthy - standby eligible for active processing",
    }


def validate_gateway_startup(
    role: str,
    update_receiver: str,
    webhook_url: str | None,
    primary_healthy: bool = True,
) -> dict[str, Any]:
    """Validate gateway startup configuration for HA correctness.

    Prevents:
    - Standby starting as active polling receiver while primary healthy
    - Dual polling receivers
    - Webhook + polling conflict
    """
    violations = []

    if role == GATEWAY_ROLE_STANDBY:
        if update_receiver == "polling" and primary_healthy:
            violations.append({
                "type": "standby_polling_while_primary_healthy",
                "message": "Standby gateway must not poll while primary is healthy",
            })

        if update_receiver == "webhook" and primary_healthy:
            violations.append({
                "type": "standby_webhook_while_primary_healthy",
                "message": "Standby gateway must not serve webhook while primary is healthy",
            })

    if role == GATEWAY_ROLE_PRIMARY:
        if update_receiver not in {"polling", "webhook", "disabled"}:
            violations.append({
                "type": "invalid_receiver_mode",
                "message": f"Invalid update receiver mode: {update_receiver}",
            })

    return {
        "ok": len(violations) == 0,
        "violations": violations,
        "role": role,
        "update_receiver": update_receiver,
    }


def record_heartbeat(
    gateway_id: str,
    state_path: Path,
    now: float | None = None,
) -> None:
    """Record heartbeat timestamp for health monitoring."""
    current_time = now if now is not None else time.time()
    heartbeat_file = state_path.parent / f"{gateway_id}.heartbeat"
    heartbeat_file.parent.mkdir(parents=True, exist_ok=True)
    heartbeat_file.write_text(json.dumps({
        "gateway_id": gateway_id,
        "heartbeat_at": current_time,
    }) + "\n", encoding="utf-8")


def read_heartbeat(gateway_id: str, state_path: Path) -> dict[str, Any]:
    """Read heartbeat data for a gateway."""
    heartbeat_file = state_path.parent / f"{gateway_id}.heartbeat"
    if not heartbeat_file.exists():
        return {"exists": False}
    try:
        data = json.loads(heartbeat_file.read_text(encoding="utf-8"))
        age = time.time() - float(data.get("heartbeat_at", 0))
        return {
            "exists": True,
            "heartbeat_at": data.get("heartbeat_at"),
            "age_seconds": round(age, 1),
            "fresh": age < HEALTH_CHECK_TIMEOUT_SECONDS,
        }
    except (json.JSONDecodeError, KeyError, ValueError):
        return {"exists": False}


def format_failover_status(failover_state: FailoverState, primary_health: dict[str, Any]) -> str:
    """Format failover status for logging/display without secrets."""
    lines = ["Telegram HA Failover Status"]
    lines.append(f"Primary healthy: {failover_state.primary_healthy}")
    lines.append(f"Primary health check: {primary_health.get('message', 'unknown')}")
    lines.append(f"State replication verified: {failover_state.replication_verified}")
    lines.append(f"Promotion blocked: {failover_state.promotion_blocked}")
    lines.append(f"Dual receiver detected: {failover_state.dual_receiver_detected}")
    if failover_state.last_promotion_attempt:
        elapsed = time.time() - failover_state.last_promotion_attempt
        lines.append(f"Last promotion attempt: {round(elapsed, 0)}s ago")
    return "\n".join(lines)
