#!/usr/bin/env python3
"""Run bounded Control Plane lease maintenance.

This watchdog intentionally talks only to the Control Plane HTTP API. It does
not inspect Redis directly and does not kill OS processes; the Control Plane
owns lease state transitions and attempt history.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_CONTROL_URL = os.environ.get("KOLIBRI_FACTORY_CONTROL_URL", "http://10.99.0.2:9101").rstrip("/")
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


def build_summary(
    health: dict[str, Any],
    rebuild: dict[str, Any] | None,
    reap: dict[str, Any],
    sweep: dict[str, Any],
    deliverable_failures: dict[str, Any] | None = None,
) -> dict[str, Any]:
    failures = deliverable_failures or {}
    return {
        "status": "ok" if health.get("status") == "ok" else "degraded",
        "redis": health.get("redis"),
        "queue_backend": health.get("queue_backend"),
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
) -> dict[str, Any]:
    started_at = utc_now()
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
    lines = [
        "# Kolibri Factory Lease Watchdog",
        "",
        f"- Started: `{report.get('started_at')}`",
        f"- Finished: `{report.get('finished_at')}`",
        f"- Control Plane: `{report.get('control_url')}`",
        f"- Status: `{summary.get('status')}`",
        f"- Redis: `{summary.get('redis')}`",
        f"- Task total: `{summary.get('task_total')}`",
        f"- Lease index total: `{summary.get('lease_index_total')}`",
        f"- Expired leases: `{summary.get('expired')}`",
        f"- Requeued expired: `{summary.get('requeued_expired')}`",
        f"- Dead-lettered expired: `{summary.get('dead_lettered_expired')}`",
        f"- Stuck heartbeat tasks: `{summary.get('stuck')}`",
        f"- Requeued stuck: `{summary.get('requeued_stuck')}`",
        f"- Dead-lettered stuck: `{summary.get('dead_lettered_stuck')}`",
        f"- Deliverable gate failures: `{summary.get('deliverable_gate_failed')}`",
        f"- Stale threshold seconds: `{summary.get('stale_after_seconds')}`",
        "",
        "```json",
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
    ]
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
    payload = urllib.parse.urlencode({"chat_id": chat_id, "text": text[:3900], "disable_web_page_preview": True}).encode("utf-8")
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
) -> dict[str, Any]:
    summary = report.get("summary") or {}
    if not should_notify(summary):
        return {"status": "skipped", "reason": "no_action"}
    if not token:
        return {"status": "skipped", "reason": "missing_token"}
    target_chat_id = chat_id or owner_chat_id_from_state(state_path)
    if not target_chat_id:
        return {"status": "skipped", "reason": "missing_chat_id"}
    body = sanitize_report_text(markdown_path.read_text(encoding="utf-8"))
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
    return {"status": "sent", "chat_id": int(target_chat_id), "parts": len(parts), "title": title}


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
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()

    try:
        report = run_watchdog(
            args.control_url,
            limit=max(0, args.limit),
            stale_after_seconds=max(1, args.stale_after_seconds),
            timeout=max(1, args.timeout),
            rebuild_indexes=args.rebuild_indexes,
        )
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        report = {
            "event": "factory_lease_watchdog",
            "control_url": args.control_url,
            "started_at": utc_now(),
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
            json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            (args.report_dir / "latest.json").write_text(json_path.read_text(encoding="utf-8"), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["summary"]["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
