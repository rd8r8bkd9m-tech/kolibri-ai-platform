#!/usr/bin/env python3
"""Safe paid-client work pipeline contracts.

The module is intentionally stdlib-only so the control plane and dispatcher can
use it without adding runtime dependencies. It builds internal task envelopes
and owner-review gates; it never sends client messages or performs payment
actions.
"""

from __future__ import annotations

import json
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PIPELINE_VERSION = "2026-07-02"
DEFAULT_BASE_REF = "origin/main"
DEFAULT_BRANCH_PREFIX = "client-work"
PUBLIC_ACTIONS = {"send_client_message", "publish_deliverable", "request_payment", "issue_invoice", "charge_payment"}
OWNER_APPROVAL_GATES = [
    "quote_send",
    "contract_or_scope_acceptance",
    "internal_task_creation",
    "public_client_message",
    "money_action",
    "final_delivery",
]
CLIENT_CHAT_SAFETY_RULES = [
    "draft_only_until_owner_approval",
    "no_public_messages_from_agents",
    "no_payment_requests_or_money_actions",
    "no_promises_of_delivery_date_without_owner_confirmation",
    "no_legal_tax_or_refund_commitments",
    "redact_secrets_credentials_and_private_infrastructure",
    "escalate_scope_changes_disputes_and_refunds_to_owner",
]
DELIVERABLE_WORKFLOW = [
    "intake_record",
    "scope_risk_review",
    "quote_draft",
    "owner_quote_approval",
    "branch_and_task_creation",
    "implementation_artifacts",
    "review_and_verification",
    "owner_delivery_approval",
    "client_reply_draft",
    "handoff_archive",
]


class ClientWorkError(ValueError):
    """Raised when a paid-client work request is unsafe or incomplete."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def safe_slug(value: str, *, fallback: str = "work") -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip().lower()).strip("-._")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug[:72] or fallback


def redact_client_text(value: Any) -> str:
    text = _text(value)
    patterns = [
        (r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*[^,\s]+", r"\1=[REDACTED]"),
        (r"(?i)bearer\s+[a-z0-9._~+/=-]+", "Bearer [REDACTED]"),
        (r"(?i)sk-[a-z0-9_-]{12,}", "secret-key-redacted"),
        (r"(?i)ghp_[a-z0-9_]{12,}", "github-token-redacted"),
        (r"(?i)github_pat_[a-z0-9_]{12,}", "github-token-redacted"),
    ]
    for pattern, replacement in patterns:
        text = re.sub(pattern, replacement, text)
    return text


def normalize_intake(body: dict[str, Any]) -> dict[str, Any]:
    client_alias = _text(body.get("client_alias") or body.get("client_name"))
    request_summary = redact_client_text(body.get("request_summary") or body.get("objective") or body.get("message"))
    repo_slug = safe_slug(_text(body.get("repo_slug") or body.get("project") or "kolibri-ai-platform"), fallback="kolibri-ai-platform")
    if not client_alias:
        raise ClientWorkError("client_alias is required")
    if not request_summary:
        raise ClientWorkError("request_summary is required")
    task_id = _text(body.get("task_id")) or f"KWORK-{uuid.uuid4().hex[:12]}"
    work_slug = safe_slug(_text(body.get("work_slug") or request_summary), fallback=task_id.lower())
    branch = _text(body.get("branch")) or f"{DEFAULT_BRANCH_PREFIX}/{safe_slug(client_alias, fallback='client')}/{work_slug}"
    intake = {
        "task_id": task_id,
        "client_alias": client_alias,
        "request_summary": request_summary,
        "repo_slug": repo_slug,
        "work_slug": work_slug,
        "branch": branch,
        "base_ref": _text(body.get("base_ref")) or DEFAULT_BASE_REF,
        "currency": _text(body.get("currency")) or "USD",
        "quote_basis": redact_client_text(body.get("quote_basis") or "draft estimate pending owner approval"),
        "deliverables": [redact_client_text(item) for item in _list(body.get("deliverables")) if _text(item)],
        "constraints": {
            "no_public_messages": True,
            "no_money_actions": True,
            "owner_approval_required": OWNER_APPROVAL_GATES,
            "client_chat_safety_rules": CLIENT_CHAT_SAFETY_RULES,
        },
        "created_at": _text(body.get("created_at")) or utc_now(),
    }
    if not intake["deliverables"]:
        intake["deliverables"] = ["scoped implementation artifact", "verification summary", "owner-approved client reply draft"]
    return intake


def quote_draft(intake: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "draft_owner_review_required",
        "currency": intake["currency"],
        "basis": intake["quote_basis"],
        "send_to_client": False,
        "money_action_allowed": False,
        "owner_review_fields": ["scope", "price", "timeline", "exclusions", "client_message"],
        "public_action_blocked": sorted(PUBLIC_ACTIONS),
    }


def client_reply_draft(intake: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "draft_owner_review_required",
        "send_to_client": False,
        "message": (
            f"Draft for {intake['client_alias']}: we captured the request for "
            f"{intake['repo_slug']} and prepared a scoped quote/delivery plan for owner review."
        ),
        "safety_rules": CLIENT_CHAT_SAFETY_RULES,
    }


def task_envelopes(intake: dict[str, Any]) -> list[dict[str, Any]]:
    base = {
        "source": "paid_client_work_pipeline",
        "client_alias": intake["client_alias"],
        "base_ref": intake["base_ref"],
        "branch": intake["branch"],
        "constraints": intake["constraints"],
        "create_review_on_complete": True,
        "review_node": "new",
    }
    implementation_task_id = f"{intake['task_id']}-IMPLEMENT"
    return [
        {
            **base,
            "task_id": f"{intake['task_id']}-INTAKE",
            "idempotency_key": f"paid-client:{intake['task_id']}:intake",
            "kind": "paid_client_intake",
            "required_capability": "business_automation",
            "objective": f"Validate paid-client intake for {intake['client_alias']}: {intake['request_summary']}",
            "write_scope": ["docs/agent/runs", "artifacts"],
            "public_action_allowed": False,
            "money_action_allowed": False,
        },
        {
            **base,
            "task_id": f"{intake['task_id']}-QUOTE",
            "idempotency_key": f"paid-client:{intake['task_id']}:quote",
            "kind": "paid_client_quote_draft",
            "required_capability": "business_automation",
            "objective": f"Draft quote and scope for owner approval: {intake['request_summary']}",
            "depends_on": [f"{intake['task_id']}-INTAKE"],
            "write_scope": ["docs/agent/runs", "artifacts"],
            "public_action_allowed": False,
            "money_action_allowed": False,
        },
        {
            **base,
            "task_id": implementation_task_id,
            "idempotency_key": f"paid-client:{intake['task_id']}:implement",
            "kind": "owner_remote_task",
            "required_capability": "generic_implementation",
            "objective": f"Implement scoped paid-client deliverables on branch {intake['branch']}: {intake['request_summary']}",
            "depends_on": [f"{intake['task_id']}-QUOTE"],
            "write_scope": ["backend", "frontend", "ops", "scripts", "docs", "tests", "artifacts"],
            "public_action_allowed": False,
            "money_action_allowed": False,
        },
        {
            **base,
            "task_id": f"{intake['task_id']}-DELIVER",
            "idempotency_key": f"paid-client:{intake['task_id']}:deliverable",
            "kind": "paid_client_deliverable_pack",
            "required_capability": "review",
            "objective": f"Package deliverables and client reply draft for owner-approved delivery: {intake['branch']}",
            "depends_on": [implementation_task_id, f"{implementation_task_id}-REVIEW"],
            "write_scope": ["docs/agent/runs", "artifacts"],
            "public_action_allowed": False,
            "money_action_allowed": False,
        },
    ]


def build_pipeline(body: dict[str, Any]) -> dict[str, Any]:
    intake = normalize_intake(body)
    envelopes = task_envelopes(intake)
    return {
        "pipeline_version": PIPELINE_VERSION,
        "status": "ready_for_owner_approval",
        "intake": intake,
        "quote": quote_draft(intake),
        "branch": {
            "name": intake["branch"],
            "base_ref": intake["base_ref"],
            "auto_push": False,
            "push_to_main_allowed": False,
            "force_push_allowed": False,
        },
        "tasks": envelopes,
        "client_chat": client_reply_draft(intake),
        "deliverable_workflow": DELIVERABLE_WORKFLOW,
        "blocked_public_actions": sorted(PUBLIC_ACTIONS),
    }


def assert_safe_pipeline(pipeline: dict[str, Any]) -> None:
    serialized = json.dumps(pipeline, ensure_ascii=False, sort_keys=True)
    forbidden_fragments = ["TELEGRAM_BOT_TOKEN", "OPENAI_API_KEY", "GITHUB_TOKEN", "ghp_", "github_pat_"]
    for fragment in forbidden_fragments:
        if fragment in serialized:
            raise ClientWorkError(f"unsafe secret-like fragment in pipeline: {fragment}")
    if pipeline.get("quote", {}).get("send_to_client") is not False:
        raise ClientWorkError("quote must remain draft-only")
    if pipeline.get("quote", {}).get("money_action_allowed") is not False:
        raise ClientWorkError("money actions must be disabled")
    if pipeline.get("client_chat", {}).get("send_to_client") is not False:
        raise ClientWorkError("client chat must remain draft-only")
    for task in pipeline.get("tasks") or []:
        if task.get("public_action_allowed") is not False:
            raise ClientWorkError(f"task {task.get('task_id')} allows public action")
        if task.get("money_action_allowed") is not False:
            raise ClientWorkError(f"task {task.get('task_id')} allows money action")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) > 1:
        raise SystemExit("usage: paid_client_work.py [intake.json]")
    body = json.loads(Path(argv[0]).read_text(encoding="utf-8")) if argv else json.load(sys.stdin)
    pipeline = build_pipeline(body)
    assert_safe_pipeline(pipeline)
    print(json.dumps(pipeline, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
