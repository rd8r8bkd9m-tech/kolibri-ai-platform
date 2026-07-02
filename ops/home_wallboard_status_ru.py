#!/usr/bin/env python3
"""Read-only Russian terminal status for Home/fallback factory wallboards."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_CONTROL_PLANE_URL = os.environ.get("KOLIBRI_CONTROL_PLANE_URL", "http://10.99.0.10:9101")
DEFAULT_PUBLIC_STATUS_URL = os.environ.get("KOLIBRI_PUBLIC_STATUS_URL", "http://127.0.0.1/api/factory/status")
DEFAULT_SERVICES = (
    "kolibri-factory-control.service",
    "kolibri-agent-host.service",
    "kolibri-mesh-control-bridge.service",
    "kolibri-telegram-gateway.service",
)


@dataclass(frozen=True)
class HttpProbe:
    url: str
    ok: bool
    status_code: int | None
    data: Any | None = None
    error: str = ""


def _join_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def fetch_json(url: str, timeout: float = 5.0) -> HttpProbe:
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "kolibri-home-wallboard-status-ru/1"})
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read(25_000_000)
            return HttpProbe(
                url=url,
                ok=200 <= response.status < 300,
                status_code=response.status,
                data=json.loads(body.decode("utf-8")),
            )
    except HTTPError as exc:
        return HttpProbe(url=url, ok=False, status_code=exc.code, error=f"HTTP {exc.code}")
    except (TimeoutError, URLError, OSError, json.JSONDecodeError) as exc:
        return HttpProbe(url=url, ok=False, status_code=None, error=type(exc).__name__)


def unwrap_data(payload: Any) -> Any:
    if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
        return payload["data"]
    return payload


def summarize_nodes(payload: Any) -> dict[str, int]:
    data = unwrap_data(payload)
    if isinstance(data, dict) and isinstance(data.get("nodes"), list):
        nodes = data["nodes"]
        return {
            "total": len(nodes),
            "online": sum(1 for node in nodes if node.get("health") == "online" or node.get("status") == "online"),
            "degraded": sum(1 for node in nodes if node.get("health") in {"degraded", "stale"} or node.get("status") in {"degraded", "stale"}),
        }
    if isinstance(data, dict) and isinstance(data.get("nodes"), dict):
        nodes = data["nodes"]
        return {
            "total": int(nodes.get("total") or 0),
            "online": int((nodes.get("states") or {}).get("online") or nodes.get("online") or 0),
            "degraded": int((nodes.get("states") or {}).get("degraded") or nodes.get("degraded") or 0),
        }
    return {"total": 0, "online": 0, "degraded": 0}


def summarize_tasks(payload: Any) -> dict[str, int]:
    data = unwrap_data(payload)
    if not isinstance(data, dict):
        return {"queued": 0, "running": 0, "total": 0}

    queue_count = len(data.get("queue") or []) if isinstance(data.get("queue"), list) else int(data.get("queued") or 0)
    tasks = data.get("tasks")
    if isinstance(tasks, list):
        running = sum(1 for task in tasks if task.get("status") in {"leased", "running"} or task.get("state") in {"leased", "running"})
        return {"queued": queue_count, "running": running, "total": max(len(tasks), queue_count + running)}
    if isinstance(tasks, dict):
        states = tasks.get("states") or {}
        running = int(tasks.get("running") or states.get("running") or states.get("leased") or 0)
        total = int(tasks.get("total") or sum(value for value in states.values() if isinstance(value, int)) or queue_count + running)
        return {"queued": int(tasks.get("queued") or states.get("queued") or queue_count), "running": running, "total": total}
    return {"queued": queue_count, "running": 0, "total": queue_count}


def service_status(service_names: tuple[str, ...] = DEFAULT_SERVICES) -> list[dict[str, str]]:
    if not service_names:
        return []
    command = [
        "systemctl",
        "show",
        *service_names,
        "--property=Id,LoadState,ActiveState,SubState,MainPID",
        "--no-pager",
    ]
    try:
        result = subprocess.run(command, check=False, text=True, capture_output=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [{"Id": "systemctl", "LoadState": "unavailable", "ActiveState": "unknown", "SubState": type(exc).__name__, "MainPID": "0"}]

    services: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if not line.strip():
            if current:
                services.append(current)
                current = {}
            continue
        key, _, value = line.partition("=")
        current[key] = value
    if current:
        services.append(current)
    return services


def render_status(
    *,
    control_health: HttpProbe,
    control_nodes: HttpProbe,
    control_tasks: HttpProbe,
    public_status: HttpProbe,
    services: list[dict[str, str]],
    now: datetime | None = None,
) -> str:
    now = now or datetime.now(timezone.utc)
    control_node_counts = summarize_nodes(control_nodes.data)
    control_task_counts = summarize_tasks(control_tasks.data)
    public_node_counts = summarize_nodes(public_status.data)
    public_task_counts = summarize_tasks(public_status.data)
    health_data = unwrap_data(control_health.data)
    redis = health_data.get("redis", "unknown") if isinstance(health_data, dict) else "unknown"
    product = public_status.data.get("product", "Колибри") if isinstance(public_status.data, dict) else "Колибри"
    runtime = public_status.data.get("runtime", "unknown") if isinstance(public_status.data, dict) else "unknown"

    visibility_gap = (
        public_status.ok
        and control_node_counts["total"] > 0
        and public_node_counts["total"] == 0
    )
    lines = [
        "Колибри Фабрика — статус автопилота",
        f"Обновлено: {now.isoformat(timespec='seconds')}",
        "",
        "Панель Home / публичный путь",
        f"- Продукт: {product}",
        f"- Runtime: {runtime}",
        f"- HTTP: {'ok' if public_status.ok else 'blocked'} ({public_status.status_code or public_status.error})",
        f"- Узлы на публичном пути: {public_node_counts['total']} всего, {public_node_counts['online']} online",
        f"- Задачи на публичном пути: {public_task_counts['total']} всего, {public_task_counts['queued']} в очереди",
        "",
        "Control Plane",
        f"- Health: {'ok' if control_health.ok else 'blocked'} ({control_health.status_code or control_health.error}), Redis: {redis}",
        f"- Узлы: {control_node_counts['total']} всего, {control_node_counts['online']} online, {control_node_counts['degraded']} degraded/stale",
        f"- Задачи: {control_task_counts['total']} всего, {control_task_counts['queued']} в очереди, {control_task_counts['running']} выполняются",
        "",
        "Сервисы",
    ]
    for service in services:
        lines.append(
            f"- {service.get('Id', 'unknown')}: {service.get('ActiveState', 'unknown')}/"
            f"{service.get('SubState', 'unknown')} pid={service.get('MainPID', '0')}"
        )
    lines.extend(
        [
            "",
            "Безопасность",
            "- Режим: read-only, без restart/start/stop и без изменений Telegram.",
            "- Секреты не читаются и не выводятся.",
            "",
            "Следующее действие",
            "- Подключить этот вывод к tmux на Home или fallback Agent Host.",
        ]
    )
    if visibility_gap:
        lines.append("- Блокер видимости: публичный путь доступен, но не отражает live Control Plane узлы/задачи.")
    return "\n".join(lines) + "\n"


def build_status(control_plane_url: str, public_status_url: str, timeout: float) -> str:
    return render_status(
        control_health=fetch_json(_join_url(control_plane_url, "/v1/health"), timeout),
        control_nodes=fetch_json(_join_url(control_plane_url, "/v1/fleet/nodes"), timeout),
        control_tasks=fetch_json(_join_url(control_plane_url, "/v1/tasks?limit=25"), timeout),
        public_status=fetch_json(public_status_url, timeout),
        services=service_status(),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Russian read-only Kolibri Home wallboard status.")
    parser.add_argument("--control-plane-url", default=DEFAULT_CONTROL_PLANE_URL)
    parser.add_argument("--public-status-url", default=DEFAULT_PUBLIC_STATUS_URL)
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args(argv)
    sys.stdout.write(build_status(args.control_plane_url, args.public_status_url, args.timeout))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
