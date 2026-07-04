#!/usr/bin/env python3
"""KFM queue steward with Control Plane fallback and owner-safe reporting."""

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_CONTROL_URLS = ("http://10.99.0.1:9101", "http://10.99.0.10:9101", "http://10.99.0.2:9101")
BATCH_LIMIT = int(os.environ.get("KOLIBRI_KFM_STEWARD_BATCH_LIMIT", "10"))
TIMEOUT_SECONDS = float(os.environ.get("KOLIBRI_KFM_STEWARD_TIMEOUT", "4"))
PREFIX = "P0_KFM_QUEUE_STEWARD_BATCH_"
STATE_DIR = Path(os.environ.get("KOLIBRI_KFM_STEWARD_STATE_DIR", "/var/lib/kolibri-agent/kfm-steward"))
LATEST = STATE_DIR / "latest.json"
SAFE_CAPS = {"read_only_probe", "mesh_node", "generic_implementation", "implementation", "runner:mimo", "runner:codex"}
ACTIVE_STATES = {"queued", "leased", "running", "review", "waiting_review", "retry_scheduled"}
DENY_TARGETS = {"home", "qjns", "new"}
DENY_PATTERNS = [
    r"cpu[_-]?quota", r"disk[_-]?cleanup", r"runner[_-]?kill", r"ssh", r"firewall", r"ufw", r"iptables",
    r"provider", r"billing", r"delete", r"rebuild", r"resize", r"rotate[_-]?keys", r"private[_-]?key",
    r"telegram[_-]?secret", r"token", r"home[_-]?noc[_-]?repair", r"home[_-]?kiosk", r"mikrotik",
]


@dataclass
class ControlProbe:
    url: str
    path: str
    reachable: bool
    http_status: int | None
    latency_ms: int
    reason: str


@dataclass
class ControlSelection:
    control_plane_used: str | None
    failed_candidates: list[ControlProbe]
    health_payload: dict[str, Any] | None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def control_urls() -> list[str]:
    raw = os.environ.get("KOLIBRI_FACTORY_CONTROL_URLS") or os.environ.get("KOLIBRI_FACTORY_CONTROL_URL")
    if not raw:
        return list(DEFAULT_CONTROL_URLS)
    values = [item.strip().rstrip("/") for item in raw.split(",") if item.strip()]
    return values or list(DEFAULT_CONTROL_URLS)


def _safe_reason(exc: Exception) -> str:
    text = str(exc)
    for marker in ("token", "secret", "password", "authorization", "cookie", "chat_id"):
        text = re.sub(marker + r"[^ ]*", "[redacted]", text, flags=re.IGNORECASE)
    return text[:240]


def request_json(base_url: str, path: str, method: str = "GET", body: dict[str, Any] | None = None, timeout: float = TIMEOUT_SECONDS) -> Any:
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = resp.read().decode("utf-8")
        return json.loads(payload) if payload else {}


def probe_control_plane(base_url: str, path: str = "/v1/health", timeout: float = TIMEOUT_SECONDS) -> tuple[ControlProbe, dict[str, Any] | None]:
    start = time.monotonic()
    try:
        payload = request_json(base_url, path, timeout=timeout)
        latency = int((time.monotonic() - start) * 1000)
        return ControlProbe(base_url.rstrip("/"), path, True, 200, latency, "ok"), payload if isinstance(payload, dict) else {}
    except urllib.error.HTTPError as exc:
        latency = int((time.monotonic() - start) * 1000)
        return ControlProbe(base_url.rstrip("/"), path, False, exc.code, latency, f"http_{exc.code}"), None
    except Exception as exc:
        latency = int((time.monotonic() - start) * 1000)
        return ControlProbe(base_url.rstrip("/"), path, False, None, latency, _safe_reason(exc)), None


def select_control_plane(urls: list[str] | None = None, timeout: float = TIMEOUT_SECONDS) -> ControlSelection:
    failed: list[ControlProbe] = []
    for base_url in urls or control_urls():
        probe, payload = probe_control_plane(base_url, timeout=timeout)
        if probe.reachable:
            return ControlSelection(probe.url, failed, payload)
        failed.append(probe)
    return ControlSelection(None, failed, None)


def env(task: dict[str, Any]) -> dict[str, Any]:
    value = task.get("envelope")
    return value if isinstance(value, dict) else {}


def val(task: dict[str, Any], *keys: str, default: Any = None) -> Any:
    envelope = env(task)
    for key in keys:
        value = task.get(key)
        if value not in (None, "", []):
            return value
        value = envelope.get(key)
        if value not in (None, "", []):
            return value
    return default


def is_active_steward(task: dict[str, Any]) -> bool:
    return str(task.get("task_id") or "").startswith(PREFIX) and str(task.get("state") or "") in ACTIVE_STATES


def stale_or_missing_target(task: dict[str, Any], live_nodes: set[str]) -> bool:
    target = str(val(task, "target_node", "required_node", default="") or "")
    if not target:
        return True
    return target not in live_nodes or target.startswith("mesh-agent-") or target.startswith("mesh-")


def safe_portable(task: dict[str, Any], live_nodes: set[str]) -> tuple[bool, str]:
    task_id = str(task.get("task_id") or "")
    state = str(task.get("state") or "")
    if state != "queued":
        return False, "not_queued"
    if task_id.startswith(PREFIX):
        return False, "steward_batch"
    envelope = env(task)
    target = str(val(task, "target_node", "required_node", default="") or "")
    cap = str(val(task, "required_capability", default="") or "")
    kind = str(val(task, "kind", default=task.get("kind") or "") or "")
    runner = str(val(task, "runner", default="") or "")
    text = json.dumps({"task_id": task_id, "target": target, "cap": cap, "kind": kind, "runner": runner, "envelope": envelope}, ensure_ascii=False).lower()
    if target in DENY_TARGETS:
        return False, "target_specific_sensitive"
    for pattern in DENY_PATTERNS:
        if re.search(pattern, text):
            return False, f"deny_pattern:{pattern}"
    if cap and cap not in SAFE_CAPS:
        return False, f"unsupported_capability:{cap}"
    if not stale_or_missing_target(task, live_nodes):
        return False, "target_is_live"
    if task_id.startswith(("P1_KWORK_KASHAPOVIA_", "P0_QUEUE_REBROADCAST_SHARD_")):
        return True, "known_safe_prefix"
    if target.startswith(("mesh-agent-", "mesh-")):
        return True, "stale_mesh_safe"
    if cap in {"read_only_probe", "mesh_node", "generic_implementation"} and runner in {"", "mimo", "codex"}:
        return True, "generic_safe"
    return False, "not_in_safe_class"


def node_ids_from_payload(payload: Any) -> set[str]:
    if not isinstance(payload, dict):
        return set()
    nodes = payload.get("nodes") or payload.get("data", {}).get("nodes") or []
    live = set()
    for node in nodes if isinstance(nodes, list) else []:
        if not isinstance(node, dict):
            continue
        if (node.get("fresh") is True or node.get("freshness") == "fresh") and str(node.get("health") or "") == "online":
            node_id = node.get("node_id")
            if node_id:
                live.add(str(node_id))
    return live


def write_latest(status: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    LATEST.write_text(json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def format_probe(probe: ControlProbe) -> str:
    status = "OK" if probe.reachable else probe.reason or "failed"
    return f"- {probe.url} — {status} ({probe.latency_ms} ms)"


def format_owner_report(status: dict[str, Any]) -> str:
    if status.get("status") == "control_plane_unavailable":
        tried = "\n".join(format_probe(ControlProbe(**item)) for item in status.get("failed_candidates", []))
        return (
            "⚠️ Kolibri Lease Watchdog\n\n"
            "Статус: не удалось проверить очередь.\n"
            "Причина: Control Plane недоступен.\n\n"
            f"Пробовал:\n{tried or '- endpoints не заданы'}\n\n"
            "Что это значит:\n"
            "Значения Redis/Tasks/Leases не проверены. Это не нули.\n\n"
            "Next:\n"
            "repair_task: P0_REPAIR_CONTROL_PLANE_API_AND_AUTHORITY_FAILOVER_20260704"
        )
    if status.get("status") in {"noop", "submitted", "diagnosed"}:
        queue_seen = status.get("queue_seen")
        queue_text = "не проверено" if queue_seen is None else str(queue_seen)
        redis = status.get("redis") or "не проверено"
        expired = status.get("expired_leases")
        expired_text = "не проверено" if expired is None else str(expired)
        stuck = status.get("stuck_heartbeat_tasks")
        stuck_text = "не проверено" if stuck is None else str(stuck)
        action = "No urgent action." if expired in (0, None) and stuck in (0, None) else "Проверить lease diagnostics."
        return (
            "✅ Kolibri Lease Watchdog\n\n"
            f"Control Plane: {status.get('control_plane_used') or 'не выбран'}\n"
            f"Redis: {redis}\n"
            f"Queue: {queue_text}\n"
            f"Expired leases: {expired_text}\n"
            f"Stuck heartbeat: {stuck_text}\n\n"
            f"Action:\n{action}"
        )
    return (
        "⚠️ Kolibri Lease Watchdog\n\n"
        "Статус: не удалось проверить очередь.\n"
        "Причина: неизвестная ошибка watchdog.\n\n"
        "Что это значит:\nЗадачи и leases не проверены. Это не нули."
    )


def queue_diagnostic_data(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data") if isinstance(payload, dict) else None
    return data if isinstance(data, dict) else payload if isinstance(payload, dict) else {}


def extract_expired_leases(payload: dict[str, Any]) -> int | None:
    data = queue_diagnostic_data(payload)
    for key in ("expired_leases", "expired_lease_total"):
        value = data.get(key)
        if isinstance(value, int):
            return value
    active_summary = data.get("active_summary")
    if isinstance(active_summary, dict) and isinstance(active_summary.get("expired_lease_total"), int):
        return active_summary["expired_lease_total"]
    return None


def extract_stuck_heartbeat_tasks(payload: dict[str, Any]) -> int | None:
    data = queue_diagnostic_data(payload)
    for key in ("stuck_heartbeat_tasks", "stuck_heartbeat_total"):
        value = data.get(key)
        if isinstance(value, int):
            return value
    return None


def send_owner_report(text: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_OWNER_CHAT_ID") or os.environ.get("TELEGRAM_REPORT_CHAT_ID")
    if not token or not chat_id:
        return
    data = json.dumps({"chat_id": chat_id, "text": text[:3900], "disable_web_page_preview": True}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        resp.read()


def steward_envelope(batch_id: str, summaries: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "task_id": batch_id,
        "idempotency_key": f"kfm-steward:{batch_id}",
        "kind": "owner_remote_task",
        "runner": "mimo",
        "target_node": "server-kfrm",
        "required_capability": "runner:mimo",
        "source": "server-kfrm:kfm-queue-steward",
        "command_node": "server-kfrm",
        "requested_role": "mimo_pool_node",
        "branch": f"codex/{batch_id.lower()}",
        "base_ref": "origin/main",
        "permission_pack": "factory_auto_permit",
        "write_scope": ["control_plane_tasks", "node_local_artifacts"],
        "max_retries": 1,
        "assigned_task_summaries": summaries,
        "constraints": {
            "max_source_tasks": BATCH_LIMIT,
            "no_secret_output": True,
            "no_source_task_cancel_delete": True,
            "remote_first": True,
        },
    }


def run(diagnose_only: bool = False, notify: bool = False) -> dict[str, Any]:
    started = utc_now()
    selection = select_control_plane()
    if not selection.control_plane_used:
        status = {
            "status": "control_plane_unavailable",
            "checked_at": utc_now(),
            "failed_candidates": [probe.__dict__ for probe in selection.failed_candidates],
            "queue_seen": None,
            "expired_leases": None,
            "stuck_heartbeat_tasks": None,
        }
        write_latest(status)
        if notify:
            send_owner_report(format_owner_report(status))
        return status

    base_url = selection.control_plane_used
    queue_diag: dict[str, Any] = {}
    try:
        queue_diag = request_json(base_url, "/v1/tasks/queue/diagnostics", timeout=TIMEOUT_SECONDS)
    except Exception:
        queue_diag = {}
    tasks_payload = request_json(base_url, "/v1/tasks", timeout=TIMEOUT_SECONDS)
    tasks = tasks_payload.get("tasks") if isinstance(tasks_payload, dict) else []
    if not isinstance(tasks, list):
        tasks = []
    if any(is_active_steward(task) for task in tasks if isinstance(task, dict)):
        status = {"status": "noop", "reason": "active_steward_exists", "control_plane_used": base_url, "checked_at": utc_now(), "queue_seen": len(tasks)}
        write_latest(status)
        return status
    try:
        live_nodes = node_ids_from_payload(request_json(base_url, "/v1/fabric/routes", timeout=TIMEOUT_SECONDS))
    except Exception:
        live_nodes = set()
    selected: list[dict[str, Any]] = []
    skipped: dict[str, int] = {}
    for task in tasks:
        if not isinstance(task, dict):
            continue
        ok, reason = safe_portable(task, live_nodes)
        if ok:
            selected.append(task)
            if len(selected) >= BATCH_LIMIT:
                break
        else:
            skipped[reason] = skipped.get(reason, 0) + 1
    if diagnose_only or not selected:
        status = {
            "status": "diagnosed" if diagnose_only else "noop",
            "reason": "diagnose_only" if diagnose_only else "no_safe_portable_tasks",
            "control_plane_used": base_url,
            "redis": (selection.health_payload or {}).get("data", {}).get("redis") or (selection.health_payload or {}).get("redis"),
            "queue_seen": len(tasks),
            "queue_diagnostics": queue_diag,
            "expired_leases": extract_expired_leases(queue_diag),
            "stuck_heartbeat_tasks": extract_stuck_heartbeat_tasks(queue_diag),
            "skipped": skipped,
            "failed_candidates": [probe.__dict__ for probe in selection.failed_candidates],
            "started_at": started,
            "finished_at": utc_now(),
        }
        write_latest(status)
        if notify:
            send_owner_report(format_owner_report(status))
        return status

    batch_id = PREFIX + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    summaries = [
        {
            "task_id": task.get("task_id"),
            "state": task.get("state"),
            "kind": val(task, "kind", default=task.get("kind")),
            "target_node": val(task, "target_node", "required_node"),
            "required_capability": val(task, "required_capability"),
            "runner": val(task, "runner"),
        }
        for task in selected
    ]
    created = request_json(base_url, "/v1/tasks", method="POST", body=steward_envelope(batch_id, summaries), timeout=TIMEOUT_SECONDS)
    status = {
        "status": "submitted",
        "task_id": batch_id,
        "control_plane_used": base_url,
        "created_state": created.get("state") if isinstance(created, dict) else None,
        "selected_count": len(selected),
        "selected_task_ids": [str(item.get("task_id")) for item in selected],
        "skipped": skipped,
        "started_at": started,
        "finished_at": utc_now(),
    }
    write_latest(status)
    if notify:
        send_owner_report(format_owner_report(status))
    return status


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--diagnose-only", action="store_true")
    parser.add_argument("--notify", action="store_true")
    args = parser.parse_args()
    status = run(diagnose_only=args.diagnose_only, notify=args.notify)
    print(json.dumps(status, ensure_ascii=False, sort_keys=True))
    return 0 if status.get("status") != "control_plane_unavailable" else 2


if __name__ == "__main__":
    raise SystemExit(main())
