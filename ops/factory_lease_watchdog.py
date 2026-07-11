#!/usr/bin/env python3
"""Run bounded Control Plane lease maintenance.

This watchdog intentionally talks only to the Control Plane HTTP API. It does
not inspect Redis directly and does not kill OS processes; the Control Plane
owns lease state transitions and attempt history.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CURRENT_DIR = Path(__file__).resolve().parent
for dependency_dir in (
    CURRENT_DIR,
    Path("/usr/local/lib/kolibri"),
    Path("/opt/kolibri-ai-platform/ops"),
    Path("/opt/kolibri-ai/ops"),
):
    if dependency_dir.exists() and str(dependency_dir) not in sys.path:
        sys.path.insert(0, str(dependency_dir))

from control_plane_endpoint import ControlPlaneEndpointError, resolve_home_control_plane_url

DEFAULT_CONTROL_URL = ""
DEFAULT_REPORT_DIR = Path(os.environ.get("KOLIBRI_FACTORY_WATCHDOG_REPORT_DIR", "/var/lib/kolibri-factory-control/watchdog"))
DEFAULT_TELEGRAM_STATE = Path(os.environ.get("TELEGRAM_GATEWAY_STATE", "/var/lib/kolibri-telegram-gateway/state.json"))
REPORT_CHUNK_LIMIT = 3600


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def http_json(method: str, url: str, body: dict[str, Any] | None = None, timeout: int = 20) -> Any:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read().decode("utf-8")
        return json.loads(payload) if payload else {}


def call_control(control_url: str, method: str, path: str, body: dict[str, Any] | None = None, timeout: int = 20) -> Any:
    suffix = path if path.startswith("/") else f"/{path}"
    return http_json(method, f"{control_url.rstrip('/')}{suffix}", body=body, timeout=timeout)


def quote_task_id(task_id: str) -> str:
    return urllib.parse.quote(str(task_id), safe="")


def fetch_task(control_url: str, task_id: str, timeout: int) -> dict[str, Any]:
    return call_control(control_url, "GET", f"/v1/tasks/{quote_task_id(task_id)}", timeout=timeout)


def build_summary(
    health: dict[str, Any],
    rebuild: dict[str, Any] | None,
    reap: dict[str, Any],
    sweep: dict[str, Any],
    deliverable_failures: dict[str, Any] | None = None,
) -> dict[str, Any]:
    failures = deliverable_failures or {}
    health_data = health.get("data") if isinstance(health.get("data"), dict) else {}
    redis_status = health.get("redis") or health_data.get("redis")
    queue_backend = health.get("queue_backend") or health_data.get("queue_backend")
    health_ok = health.get("status") in {"ok", "completed"} and redis_status == "PONG"
    return {
        "status": "ok" if health_ok else "degraded",
        "redis": redis_status,
        "queue_backend": queue_backend,
        "rebuild_indexed": None if rebuild is None else rebuild.get("indexed"),
        "task_total": sweep.get("task_total", reap.get("task_total")),
        "lease_index_total": sweep.get("lease_index_total", reap.get("lease_index_total")),
        "expired": reap.get("expired"),
        "requeued_expired": reap.get("requeued_total"),
        "dead_lettered_expired": reap.get("dead_lettered_total"),
        "stuck": sweep.get("stuck"),
        "requeued_stuck": sweep.get("requeued_total"),
        "dead_lettered_stuck": sweep.get("dead_lettered_total"),
        "stale_after_seconds": sweep.get("stale_after_seconds"),
        "deliverable_gate_status": "ok" if deliverable_failures is not None else "unavailable",
        "deliverable_gate_failed": int_value(failures.get("total")),
        "deliverable_gate_recent": failures.get("tasks") if isinstance(failures.get("tasks"), list) else [],
    }


def should_notify(summary: dict[str, Any]) -> bool:
    if summary.get("status") != "ok":
        return True
    for key in (
        "expired",
        "requeued_expired",
        "dead_lettered_expired",
        "stuck",
        "requeued_stuck",
        "dead_lettered_stuck",
        "deliverable_gate_new",
        "deliverable_retry_failed",
    ):
        try:
            if int(summary.get(key) or 0) > 0:
                return True
        except (TypeError, ValueError):
            return True
    return False


def run_watchdog(
    control_url: str,
    limit: int,
    stale_after_seconds: int,
    timeout: int,
    rebuild_indexes: bool = False,
    started_at: str | None = None,
) -> dict[str, Any]:
    started_at = started_at or utc_now()
    health = call_control(control_url, "GET", "/v1/health", timeout=timeout)
    rebuild = (
        call_control(control_url, "POST", "/v1/tasks/rebuild-indexes", timeout=timeout)
        if rebuild_indexes
        else None
    )
    reap = call_control(control_url, "POST", "/v1/tasks/reap-expired", {"limit": limit}, timeout=timeout)
    sweep = call_control(
        control_url,
        "POST",
        "/v1/tasks/sweep-stuck",
        {"limit": limit, "stale_after_seconds": stale_after_seconds},
        timeout=timeout,
    )
    try:
        deliverable_failures = call_control(
            control_url,
            "GET",
            f"/v1/tasks/failures?error_type=deliverable_gate_failed&limit={limit}",
            timeout=timeout,
        )
    except (OSError, urllib.error.URLError, TimeoutError):
        deliverable_failures = None
    finished_at = utc_now()
    report = {
        "event": "factory_lease_watchdog",
        "control_url": control_url,
        "started_at": started_at,
        "finished_at": finished_at,
        "limit": limit,
        "rebuild_indexes": rebuild_indexes,
        "health": health,
        "rebuild": rebuild,
        "reap_expired": reap,
        "sweep_stuck": sweep,
        "deliverable_failures": deliverable_failures,
    }
    report["summary"] = build_summary(health, rebuild, reap, sweep, deliverable_failures)
    return report


def markdown_report(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    def shown(value: Any) -> Any:
        return "не собрано" if value is None else value

    lines = [
        "# Kolibri Factory Lease Watchdog",
        "",
        f"- Started: `{report.get('started_at')}`",
        f"- Finished: `{report.get('finished_at')}`",
        f"- Control Plane: `{report.get('control_url')}`",
        f"- Status: `{summary.get('status')}`",
        f"- Redis: `{shown(summary.get('redis'))}`",
        f"- Task total: `{shown(summary.get('task_total'))}`",
        f"- Lease index total: `{shown(summary.get('lease_index_total'))}`",
        f"- Expired leases: `{shown(summary.get('expired'))}`",
        f"- Requeued expired: `{shown(summary.get('requeued_expired'))}`",
        f"- Dead-lettered expired: `{shown(summary.get('dead_lettered_expired'))}`",
        f"- Stuck heartbeat tasks: `{shown(summary.get('stuck'))}`",
        f"- Requeued stuck: `{shown(summary.get('requeued_stuck'))}`",
        f"- Dead-lettered stuck: `{shown(summary.get('dead_lettered_stuck'))}`",
        f"- Deliverable gate failures: `{shown(summary.get('deliverable_gate_failed'))}`",
        f"- New deliverable gate failures: `{shown(summary.get('deliverable_gate_new'))}`",
        f"- Deliverable retry created: `{shown(summary.get('deliverable_retry_created'))}`",
        f"- Deliverable retry failed: `{shown(summary.get('deliverable_retry_failed'))}`",
        f"- Stale threshold seconds: `{shown(summary.get('stale_after_seconds'))}`",
        "",
        "```json",
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
    ]
    if report.get("error") or summary.get("error"):
        lines[5:5] = [f"- Error: `{report.get('error') or summary.get('error')}`"]
    return "\n".join(lines)


def sanitize_report_text(text: str) -> str:
    redacted_lines = []
    secret_pattern = re.compile(r"(token|secret|password|passwd|api_key|access_token|refresh_token|client_secret)(\s*[=:]\s*)[^\s`]+", re.I)
    for line in text.splitlines():
        lowered = line.lower()
        if any(marker in lowered for marker in ("-----begin", "private key", "authorization:", "cookie:", "set-cookie:")):
            redacted_lines.append("[REDACTED SECRET LINE]")
            continue
        redacted_lines.append(secret_pattern.sub(r"\1\2[REDACTED]", line))
    return "\n".join(redacted_lines)


def readable_report_text(text: str) -> str:
    lines: list[str] = []
    in_json_block = False
    removed_json_blocks = 0
    for line in text.splitlines():
        marker = line.strip().lower()
        if marker.startswith("```json"):
            in_json_block = True
            removed_json_blocks += 1
            continue
        if in_json_block:
            if marker.startswith("```"):
                in_json_block = False
            continue
        lines.append(line)
    readable = sanitize_report_text("\n".join(lines)).strip()
    if removed_json_blocks:
        readable = (
            f"{readable}\n\n"
            "Полный JSON: сохранён в артефакте watchdog-отчёта; в Telegram не отправляю сырой JSON."
        ).strip()
    return readable or "Краткий отчёт пустой; полный JSON сохранён в артефактах."


def escape_telegram_html(value: Any) -> str:
    text = "" if value is None else str(value)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
        .replace("’", "&#39;")
    )


def split_telegram_text(text: str, limit: int = REPORT_CHUNK_LIMIT) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    current = ""
    for paragraph in text.split("\n\n"):
        candidate = paragraph if not current else f"{current}\n\n{paragraph}"
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            parts.append(current)
        while len(paragraph) > limit:
            parts.append(paragraph[:limit])
            paragraph = paragraph[limit:]
        current = paragraph
    if current:
        parts.append(current)
    return parts or ["Пустой отчёт."]


def owner_chat_id_from_state(state_path: Path) -> int | None:
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    chat_id = data.get("owner_chat_id")
    if chat_id:
        return int(chat_id)
    for record in (data.get("tracked") or {}).values():
        if isinstance(record, dict) and record.get("chat_id"):
            return int(record["chat_id"])
    return None


def send_telegram_message(token: str, chat_id: int, text: str, timeout: int = 35) -> dict[str, Any]:
    html_text = escape_telegram_html(text)
    payload = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": html_text[:4096],
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
    ).encode("utf-8")
    request = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=payload, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        result = json.loads(response.read().decode("utf-8"))
    if not result.get("ok"):
        raise RuntimeError("telegram sendMessage failed")
    return result.get("result") or {}


def maybe_send_telegram_report(
    report: dict[str, Any],
    markdown_path: Path,
    *,
    token: str | None,
    chat_id: int | None,
    state_path: Path,
    title: str,
    timeout: int,
    incident_state_path: Path | None = None,
) -> dict[str, Any]:
    summary = report.get("summary") or {}
    notification_state = incident_state_path or markdown_path.parent / "telegram-notification-state.json"
    if not should_notify(summary):
        _write_notification_state(notification_state, {"active_fingerprint": None, "healthy_at": utc_now()})
        return {"status": "skipped", "reason": "no_action"}
    if not token:
        return {"status": "skipped", "reason": "missing_token"}
    target_chat_id = chat_id or owner_chat_id_from_state(state_path)
    if not target_chat_id:
        return {"status": "skipped", "reason": "missing_chat_id"}
    fingerprint_payload = {
        "status": str(summary.get("status") or "unknown"),
        "error_class": str(summary.get("error") or report.get("error") or "").split(":", 1)[0][:160],
        "actions": {key: int_value(summary.get(key)) for key in (
            "expired", "requeued_expired", "dead_lettered_expired", "stuck",
            "requeued_stuck", "dead_lettered_stuck", "deliverable_gate_new",
            "deliverable_retry_failed",
        )},
    }
    fingerprint = hashlib.sha256(
        json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    previous = _read_notification_state(notification_state)
    if previous.get("active_fingerprint") == fingerprint:
        return {"status": "skipped", "reason": "duplicate_incident"}
    body = readable_report_text(markdown_path.read_text(encoding="utf-8"))
    prefix = "\n".join(
        [
            f"Тема: {title}",
            f"Дата: {utc_now()}",
            "Ответственный: Kolibri lease watchdog",
            f"Статус: {summary.get('status')}",
            "",
        ]
    )
    parts = split_telegram_text(prefix + body)
    for index, part in enumerate(parts, start=1):
        heading = f"{title} ({index}/{len(parts)})\n\n" if len(parts) > 1 else ""
        send_telegram_message(token, int(target_chat_id), heading + part, timeout=timeout)
    _write_notification_state(
        notification_state,
        {"active_fingerprint": fingerprint, "sent_at": utc_now(), "status": fingerprint_payload["status"]},
    )
    return {"status": "sent", "chat_id": int(target_chat_id), "parts": len(parts), "title": title}


def _read_notification_state(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_notification_state(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def action_totals(summary: dict[str, Any]) -> dict[str, int]:
    return {
        "expired": int_value(summary.get("expired")),
        "stuck": int_value(summary.get("stuck")),
        "requeued_expired": int_value(summary.get("requeued_expired")),
        "requeued_stuck": int_value(summary.get("requeued_stuck")),
        "dead_lettered_expired": int_value(summary.get("dead_lettered_expired")),
        "dead_lettered_stuck": int_value(summary.get("dead_lettered_stuck")),
        "deliverable_gate_failed": int_value(summary.get("deliverable_gate_new")),
    }


def empty_rollup(now: str) -> dict[str, Any]:
    return {
        "event": "factory_lease_watchdog_rollup",
        "created_at": now,
        "updated_at": now,
        "runs_total": 0,
        "runs_ok": 0,
        "runs_degraded": 0,
        "runs_failed": 0,
        "actions_total": 0,
        "totals": {
            "expired": 0,
            "stuck": 0,
            "requeued_expired": 0,
            "requeued_stuck": 0,
            "dead_lettered_expired": 0,
            "dead_lettered_stuck": 0,
            "deliverable_gate_failed": 0,
        },
        "last_summary": {},
        "recent_actions": [],
        "deliverable_gate_seen_task_ids": [],
    }


def load_rollup(report_dir: Path, now: str) -> dict[str, Any]:
    path = report_dir / "summary.json"
    try:
        rollup = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty_rollup(now)
    base = empty_rollup(now)
    base.update(rollup if isinstance(rollup, dict) else {})
    totals = base.setdefault("totals", {})
    for key in empty_rollup(now)["totals"]:
        totals[key] = int_value(totals.get(key))
    base.setdefault("recent_actions", [])
    base.setdefault("deliverable_gate_seen_task_ids", [])
    return base


def deliverable_gate_task_ids(summary: dict[str, Any]) -> list[str]:
    ids = []
    for item in summary.get("deliverable_gate_recent") or []:
        if isinstance(item, dict) and item.get("task_id"):
            ids.append(str(item["task_id"]))
    return ids


def normalize_acceptance(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def build_deliverable_retry_envelope(source_task: dict[str, Any], now: str | None = None) -> dict[str, Any]:
    source_task_id = str(source_task.get("task_id") or "").strip()
    if not source_task_id:
        raise ValueError("source task_id is required")
    source_envelope = source_task.get("envelope") if isinstance(source_task.get("envelope"), dict) else {}
    envelope = dict(source_envelope)
    envelope["task_id"] = f"{source_task_id}-DELIVERABLE-RETRY"
    envelope["idempotency_key"] = f"deliverable-retry:{source_task_id}"
    envelope["kind"] = envelope.get("kind") or source_task.get("kind") or "generic_implementation"
    envelope["source_task_id"] = source_task_id
    envelope["retry_reason"] = "deliverable_gate_failed"
    envelope["required_capability"] = envelope.get("required_capability") or "generic_implementation"
    envelope["max_retries"] = max(1, int_value(envelope.get("max_retries")) or 1)
    target_node = str(envelope.get("target_node") or envelope.get("required_node") or "")
    if target_node.startswith("__"):
        envelope.pop("target_node", None)
        envelope.pop("required_node", None)

    original_objective = (
        envelope.get("objective")
        or envelope.get("goal")
        or envelope.get("message")
        or source_task.get("error")
        or f"Исправить deliverable gate для {source_task_id}"
    )
    envelope["objective"] = (
        f"{original_objective}\n\n"
        f"Retry source task: {source_task_id}. Previous completion was rejected by deliverable gate. "
        "Execute the task fully: create a real code/doc/artifact delta, run relevant checks, commit and push the branch, "
        "then return result_reference, changed_files, checks, and commit/PR evidence."
    )
    acceptance = normalize_acceptance(envelope.get("acceptance") or envelope.get("acceptance_criteria"))
    required_items = [
        "Produce a non-empty git diff or explicit artifact/code delta.",
        "Run relevant tests/checks and include commands in result.checks.",
        "Commit and push the branch, or include a PR URL.",
        "Return result_reference, changed_files, checks, and commit/PR evidence.",
    ]
    seen = {item.casefold() for item in acceptance}
    for item in required_items:
        if item.casefold() not in seen:
            acceptance.append(item)
            seen.add(item.casefold())
    envelope["acceptance"] = acceptance
    envelope["source"] = {
        "kind": "watchdog_deliverable_retry",
        "source_task_id": source_task_id,
        "created_at": now or utc_now(),
    }
    envelope.setdefault("create_review_on_complete", False)
    return envelope


def create_deliverable_retry_tasks(report: dict[str, Any], control_url: str, timeout: int) -> dict[str, Any]:
    summary = report.setdefault("summary", {})
    task_ids = [str(item) for item in (summary.get("deliverable_gate_new_task_ids") or []) if str(item).strip()]
    created: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for task_id in task_ids:
        try:
            source_task = fetch_task(control_url, task_id, timeout=timeout)
            retry_envelope = build_deliverable_retry_envelope(source_task)
            retry_task = call_control(control_url, "POST", "/v1/tasks", retry_envelope, timeout=timeout)
            created.append(
                {
                    "source_task_id": task_id,
                    "task_id": retry_task.get("task_id"),
                    "state": retry_task.get("state"),
                    "idempotency_key": retry_task.get("idempotency_key"),
                }
            )
        except Exception as exc:  # pragma: no cover - exact network failures are environment-specific
            failed.append({"source_task_id": task_id, "error": str(exc)})
    result = {"created": created, "failed": failed}
    report["deliverable_retries"] = result
    summary["deliverable_retry_created"] = len(created)
    summary["deliverable_retry_failed"] = len(failed)
    return result


def update_rollup(report: dict[str, Any], report_dir: Path) -> dict[str, Any]:
    now = utc_now()
    report_dir.mkdir(parents=True, exist_ok=True)
    summary = report.get("summary") or {}
    rollup = load_rollup(report_dir, now)
    rollup["updated_at"] = now
    rollup["runs_total"] = int_value(rollup.get("runs_total")) + 1
    status = str(summary.get("status") or "failed")
    if status == "ok":
        rollup["runs_ok"] = int_value(rollup.get("runs_ok")) + 1
    elif status == "degraded":
        rollup["runs_degraded"] = int_value(rollup.get("runs_degraded")) + 1
    else:
        rollup["runs_failed"] = int_value(rollup.get("runs_failed")) + 1
    totals = rollup.setdefault("totals", {})
    seen_gate_ids = set(str(item) for item in (rollup.get("deliverable_gate_seen_task_ids") or []))
    current_gate_ids = deliverable_gate_task_ids(summary)
    new_gate_ids = [task_id for task_id in current_gate_ids if task_id not in seen_gate_ids]
    summary["deliverable_gate_new"] = len(new_gate_ids)
    summary["deliverable_gate_new_task_ids"] = new_gate_ids
    if current_gate_ids:
        rollup["deliverable_gate_seen_task_ids"] = sorted((seen_gate_ids | set(current_gate_ids)))[-500:]
    current_actions = action_totals(summary)
    action_count = sum(current_actions.values())
    rollup["actions_total"] = int_value(rollup.get("actions_total")) + action_count
    for key, value in current_actions.items():
        totals[key] = int_value(totals.get(key)) + value
    rollup["last_summary"] = summary
    if action_count or status != "ok":
        recent = list(rollup.get("recent_actions") or [])
        recent.insert(
            0,
            {
                "at": report.get("finished_at") or now,
                "status": status,
                "summary": summary,
                "actions": current_actions,
            },
        )
        rollup["recent_actions"] = recent[:20]
    (report_dir / "summary.json").write_text(json.dumps(rollup, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (report_dir / "latest-summary.md").write_text(markdown_rollup(rollup), encoding="utf-8")
    return rollup


def markdown_rollup(rollup: dict[str, Any]) -> str:
    totals = rollup.get("totals") or {}
    lines = [
        "# Kolibri Factory Lease Watchdog Summary",
        "",
        f"- Created: `{rollup.get('created_at')}`",
        f"- Updated: `{rollup.get('updated_at')}`",
        f"- Runs total: `{rollup.get('runs_total')}`",
        f"- Runs ok: `{rollup.get('runs_ok')}`",
        f"- Runs degraded: `{rollup.get('runs_degraded')}`",
        f"- Runs failed: `{rollup.get('runs_failed')}`",
        f"- Actions total: `{rollup.get('actions_total')}`",
        f"- Expired leases: `{totals.get('expired')}`",
        f"- Stuck tasks: `{totals.get('stuck')}`",
        f"- Requeued expired: `{totals.get('requeued_expired')}`",
        f"- Requeued stuck: `{totals.get('requeued_stuck')}`",
        f"- Dead-lettered expired: `{totals.get('dead_lettered_expired')}`",
        f"- Dead-lettered stuck: `{totals.get('dead_lettered_stuck')}`",
        f"- New deliverable gate failures: `{totals.get('deliverable_gate_failed')}`",
        "",
    ]
    recent = rollup.get("recent_actions") or []
    if recent:
        lines.extend(["## Recent Actions", ""])
        for item in recent[:10]:
            actions = item.get("actions") or {}
            active = ", ".join(f"{key}={value}" for key, value in actions.items() if int_value(value))
            lines.append(f"- `{item.get('at')}` status=`{item.get('status')}` {active or 'problem'}")
        lines.append("")
    return "\n".join(lines)


def write_reports(report: dict[str, Any], report_dir: Path) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = report_dir / f"factory-lease-watchdog-{stamp}.json"
    md_path = report_dir / f"factory-lease-watchdog-{stamp}.md"
    report["rollup"] = update_rollup(report, report_dir)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(markdown_report(report), encoding="utf-8")
    latest_json = report_dir / "latest.json"
    latest_md = report_dir / "latest.md"
    latest_json.write_text(json_path.read_text(encoding="utf-8"), encoding="utf-8")
    latest_md.write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")
    return json_path, md_path


def refresh_report_files(report: dict[str, Any], json_path: Path, md_path: Path, report_dir: Path) -> None:
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(markdown_report(report), encoding="utf-8")
    (report_dir / "latest.json").write_text(json_path.read_text(encoding="utf-8"), encoding="utf-8")
    (report_dir / "latest.md").write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--control-url", default=DEFAULT_CONTROL_URL)
    parser.add_argument("--limit", type=int, default=int(os.environ.get("KOLIBRI_FACTORY_WATCHDOG_LIMIT", "50")))
    parser.add_argument("--stale-after-seconds", type=int, default=int(os.environ.get("KOLIBRI_FACTORY_WATCHDOG_STALE_AFTER", "3600")))
    parser.add_argument("--timeout", type=int, default=int(os.environ.get("KOLIBRI_FACTORY_WATCHDOG_TIMEOUT", "20")))
    parser.add_argument("--rebuild-indexes", action="store_true")
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--telegram-on-action", action="store_true")
    parser.add_argument("--telegram-state-file", type=Path, default=DEFAULT_TELEGRAM_STATE)
    parser.add_argument("--telegram-chat-id", type=int, default=int(os.environ["TELEGRAM_REPORT_CHAT_ID"]) if os.environ.get("TELEGRAM_REPORT_CHAT_ID") else None)
    parser.add_argument("--telegram-title", default=os.environ.get("KOLIBRI_FACTORY_WATCHDOG_TELEGRAM_TITLE", "Kolibri Factory Lease Watchdog"))
    parser.add_argument("--disable-deliverable-retry", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()

    try:
        args.control_url = resolve_home_control_plane_url(args.control_url or None)
    except ControlPlaneEndpointError as exc:
        parser.error(f"canonical Home Control Plane unresolved: {exc}")

    started_at = utc_now()
    try:
        report = run_watchdog(
            args.control_url,
            limit=max(0, args.limit),
            stale_after_seconds=max(1, args.stale_after_seconds),
            timeout=max(1, args.timeout),
            rebuild_indexes=args.rebuild_indexes,
            started_at=started_at,
        )
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        report = {
            "event": "factory_lease_watchdog",
            "control_url": args.control_url,
            "started_at": started_at,
            "finished_at": utc_now(),
            "summary": {"status": "failed", "error": str(exc)},
            "error": str(exc),
        }
        if not args.no_write:
            _json_path, md_path = write_reports(report, args.report_dir)
            if args.telegram_on_action:
                report["telegram"] = maybe_send_telegram_report(
                    report,
                    md_path,
                    token=os.environ.get("TELEGRAM_BOT_TOKEN"),
                    chat_id=args.telegram_chat_id,
                    state_path=args.telegram_state_file,
                    title=args.telegram_title,
                    timeout=max(1, args.timeout),
                )
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 2

    if not args.no_write:
        json_path, md_path = write_reports(report, args.report_dir)
        report["report_paths"] = {"json": str(json_path), "markdown": str(md_path)}
        if not args.disable_deliverable_retry:
            create_deliverable_retry_tasks(report, args.control_url, timeout=max(1, args.timeout))
            refresh_report_files(report, json_path, md_path, args.report_dir)
        if args.telegram_on_action:
            report["telegram"] = maybe_send_telegram_report(
                report,
                md_path,
                token=os.environ.get("TELEGRAM_BOT_TOKEN"),
                chat_id=args.telegram_chat_id,
                state_path=args.telegram_state_file,
                title=args.telegram_title,
                timeout=max(1, args.timeout),
            )
            refresh_report_files(report, json_path, md_path, args.report_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["summary"]["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
