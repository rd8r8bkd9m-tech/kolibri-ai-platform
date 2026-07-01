#!/usr/bin/env python3
"""Contracts for the Kolibri Telegram Superfactory command layer.

The module is intentionally standard-library-only so it can be imported by the
gateway, control plane, tests, and deployment checks without extending runtime
dependencies.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import urllib.parse
from collections import namedtuple
from typing import Any


CANONICAL_RECEIVER_ID = "kolibri-telegram-gateway"
VALID_RECEIVER_MODES = {"polling", "webhook", "disabled"}
RUNNER_ORDER = ("codex", "mimo", "api", "local_llm")
SECRET_ENV_NAMES = {
    "api": ("OPENAI_API_KEY", "KOLIBRI_API_RUNNER_TOKEN"),
    "local_llm": ("KOLIBRI_LOCAL_LLM_URL",),
}


ReceiverPlan = namedtuple("ReceiverPlan", "receiver_id mode should_poll webhook_url conflict startup_action")


def receiver_mode_from_env(env: dict[str, str] | None = None) -> str:
    value = (env or os.environ).get("TELEGRAM_UPDATE_RECEIVER", "polling").strip().lower()
    if value not in VALID_RECEIVER_MODES:
        raise ValueError(f"unsupported Telegram receiver mode: {value}")
    return value


def plan_update_receiver(
    env: dict[str, str] | None = None,
    webhook_info: dict[str, Any] | None = None,
) -> ReceiverPlan:
    env = env or os.environ
    mode = receiver_mode_from_env(env)
    receiver_id = env.get("TELEGRAM_RECEIVER_ID", CANONICAL_RECEIVER_ID)
    webhook_url = (webhook_info or {}).get("url") or env.get("TELEGRAM_WEBHOOK_URL") or None
    if mode == "disabled":
        return ReceiverPlan(receiver_id, mode, False, webhook_url, None, "disabled")
    if mode == "webhook":
        if not webhook_url:
            return ReceiverPlan(receiver_id, mode, False, None, "webhook_url_missing", "refuse_polling")
        return ReceiverPlan(receiver_id, mode, False, webhook_url, None, "webhook_only")
    if webhook_url:
        return ReceiverPlan(receiver_id, mode, False, webhook_url, "webhook_already_configured", "refuse_polling")
    return ReceiverPlan(receiver_id, mode, True, None, None, "poll")


def _parse_init_data(init_data: str) -> dict[str, str]:
    parsed = urllib.parse.parse_qsl(init_data, keep_blank_values=True, strict_parsing=False)
    return {key: value for key, value in parsed}


def validate_telegram_init_data(
    init_data: str,
    bot_token: str,
    owner_ids: set[int],
    admin_ids: set[int] | None = None,
    max_age_seconds: int = 86400,
    now: int | None = None,
) -> dict[str, Any]:
    """Validate Telegram Web App initData and enforce owner/admin gates."""

    if not init_data or not bot_token:
        return {"ok": False, "error": "missing_init_data_or_token"}
    fields = _parse_init_data(init_data)
    received_hash = fields.pop("hash", "")
    if not received_hash:
        return {"ok": False, "error": "hash_missing"}
    data_check = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    expected = hmac.new(secret_key, data_check.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received_hash):
        return {"ok": False, "error": "hash_mismatch"}

    auth_date = int(fields.get("auth_date") or "0")
    current = int(now if now is not None else time.time())
    if auth_date <= 0 or current - auth_date > max_age_seconds:
        return {"ok": False, "error": "auth_date_expired"}

    try:
        user = json.loads(fields.get("user") or "{}")
    except json.JSONDecodeError:
        return {"ok": False, "error": "user_invalid"}
    user_id = int(user.get("id") or 0)
    allowed = set(owner_ids) | set(admin_ids or set())
    if user_id not in allowed:
        return {"ok": False, "error": "forbidden"}
    return {"ok": True, "user": user, "role": "owner" if user_id in owner_ids else "admin"}


def runner_policy(env: dict[str, str] | None = None) -> dict[str, Any]:
    env = env or os.environ
    configured = [
        item.strip().lower()
        for item in env.get("KOLIBRI_RUNNER_POLICY", ",".join(RUNNER_ORDER)).split(",")
        if item.strip()
    ]
    ordered = [runner for runner in configured if runner in RUNNER_ORDER]
    if not ordered:
        ordered = list(RUNNER_ORDER)
    diagnostics = []
    for runner in ordered:
        required_env = SECRET_ENV_NAMES.get(runner, ())
        missing = [name for name in required_env if not env.get(name)]
        diagnostics.append({
            "runner": runner,
            "available": not missing,
            "missing_configuration": missing,
        })
    return {"ordered_runners": ordered, "diagnostics": diagnostics}


def select_runner(kind: str, requested: str | None = None, env: dict[str, str] | None = None) -> dict[str, Any]:
    env = env or os.environ
    policy = runner_policy(env)
    requested = (requested or "").strip().lower()
    if requested in {"image", "codex", "mimo", "api", "local_llm"}:
        selected = requested
    elif kind == "telegram_image_generation":
        selected = "image"
    else:
        selected = policy["ordered_runners"][0]

    diagnostics = policy["diagnostics"]
    if selected == "image":
        missing = []
        if not env.get("KOLIBRI_IMAGE_GENERATOR_CMD") and not env.get("OPENAI_API_KEY"):
            missing = ["KOLIBRI_IMAGE_GENERATOR_CMD or OPENAI_API_KEY"]
        diagnostics = [{"runner": "image", "available": not missing, "missing_configuration": missing}] + diagnostics
    return {"runner": selected, "policy": policy["ordered_runners"], "diagnostics": diagnostics}


def redacted_receiver_status(plan: ReceiverPlan) -> dict[str, Any]:
    return {
        "receiver_id": plan.receiver_id,
        "mode": plan.mode,
        "should_poll": plan.should_poll,
        "webhook_configured": bool(plan.webhook_url),
        "conflict": plan.conflict,
        "startup_action": plan.startup_action,
    }
