#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import textwrap
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(os.environ.get("KOLIBRI_REPO_ROOT", Path(__file__).resolve().parents[1]))
CONTROL_URL = os.environ.get("KOLIBRI_FACTORY_CONTROL_URL", "http://127.0.0.1:9101").rstrip("/")
SESSION = os.environ.get("KOLIBRI_HOME_SCREEN_SESSION", "kolibri-factory-screen")
REFRESH_SECONDS = int(os.environ.get("KOLIBRI_HOME_SCREEN_REFRESH", "15"))
MAX_LINES = int(os.environ.get("KOLIBRI_HOME_SCREEN_LINES", "32"))
FIXTURE_DIR = os.environ.get("KOLIBRI_HOME_SCREEN_FIXTURE_DIR")

SECRET_RE = re.compile(
    r"(?i)(token|secret|password|passwd|authorization|cookie|api[_-]?key|bot[_-]?token)"
    r"(\s*[=:]\s*|\s+)[^\s`'\"|]+"
)

PANE_TITLES = {
    "overview": "ОБЗОР",
    "tasks": "ЗАДАЧИ",
    "agents": "АГЕНТЫ",
    "prs": "PR / CI",
    "logs": "ЛОГИ",
    "blockers": "БЛОКЕРЫ",
    "owner": "ИНСТРУКЦИИ ВЛАДЕЛЬЦА",
}


def redact(text: Any) -> str:
    return SECRET_RE.sub(lambda m: f"{m.group(1)}=<redacted>", str(text))


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def title(name: str) -> str:
    label = PANE_TITLES[name]
    return f"Kolibri Factory Home | {label} | обновлено {now()}\n" + ("=" * 78)


def _fixture(name: str) -> Any | None:
    if not FIXTURE_DIR:
        return None
    path = Path(FIXTURE_DIR) / f"{name}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def fetch_json(path: str, fixture_name: str, timeout: float = 2.0) -> Any:
    fixture = _fixture(fixture_name)
    if fixture is not None:
        return fixture
    url = f"{CONTROL_URL}/v1{path}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return {"ok": False, "error": exc.__class__.__name__, "url": url}


def read_text(path: Path, limit: int = MAX_LINES) -> list[str]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return [f"нет файла: {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}"]
    return [redact(line) for line in lines[:limit]]


def shorten(value: Any, width: int = 96) -> str:
    text = redact(value)
    return text if len(text) <= width else f"{text[: width - 1]}…"


def task_rows(tasks_payload: Any) -> list[dict[str, Any]]:
    tasks = tasks_payload.get("tasks") if isinstance(tasks_payload, dict) else tasks_payload
    if isinstance(tasks, dict):
        tasks = list(tasks.values())
    return [task for task in tasks or [] if isinstance(task, dict)]


def node_rows(nodes_payload: Any) -> list[dict[str, Any]]:
    nodes = nodes_payload.get("nodes") if isinstance(nodes_payload, dict) else nodes_payload
    return [node for node in nodes or [] if isinstance(node, dict)]


def render_overview() -> str:
    health = fetch_json("/health", "health")
    nodes = node_rows(fetch_json("/nodes", "nodes"))
    tasks = task_rows(fetch_json("/tasks", "tasks"))
    running = [task for task in tasks if str(task.get("state")) in {"running", "leased"}]
    queued = [task for task in tasks if str(task.get("state")) == "queued"]
    fresh = [node for node in nodes if str(node.get("freshness") or node.get("status")) in {"fresh", "online"}]
    degraded = [node for node in nodes if str(node.get("freshness") or node.get("status")) in {"degraded", "stale", "offline"}]
    lines = [
        title("overview"),
        f"Control Plane: {shorten(health.get('status', health.get('ok', 'unknown')))} | backend: {shorten(health.get('queue_backend', 'unknown'))}",
        f"Серверы: всего {len(nodes)} | свежие {len(fresh)} | требуют внимания {len(degraded)}",
        f"Задачи: активные {len(running)} | в очереди {len(queued)} | всего видно {len(tasks)}",
        f"Источник: {CONTROL_URL}/v1/* | секреты на экран не выводятся",
        "",
        "Быстрые команды:",
        f"  tmux attach -t {SESSION}",
        f"  ops/kolibri-home-screen stop        # rollback: остановить только tmux-пульт",
        f"  systemctl --user stop kolibri-home-screen.service",
    ]
    return "\n".join(lines)


def render_tasks() -> str:
    tasks = sorted(task_rows(fetch_json("/tasks", "tasks")), key=lambda t: str(t.get("updated_at") or t.get("created_at") or ""), reverse=True)
    lines = [title("tasks")]
    if not tasks:
        lines.append("Активные задачи не получены или очередь пуста.")
    for task in tasks[:MAX_LINES]:
        lines.append(
            f"{shorten(task.get('state', 'unknown'), 10):10} "
            f"{shorten(task.get('task_id') or task.get('id'), 58):58} "
            f"lease={shorten(task.get('lease_owner') or '-', 24)}"
        )
        objective = task.get("objective") or task.get("goal") or task.get("error_type")
        if objective:
            lines.append(f"  {shorten(objective, 110)}")
    return "\n".join(lines)


def render_agents() -> str:
    nodes = node_rows(fetch_json("/nodes", "nodes"))
    lines = [title("agents")]
    if not nodes:
        lines.append("Агенты/серверы не получены.")
    for node in nodes[:MAX_LINES]:
        node_id = node.get("node_id") or node.get("id") or "unknown"
        caps = ", ".join(str(cap) for cap in node.get("capabilities") or []) or "-"
        lines.append(
            f"{shorten(node_id, 18):18} "
            f"{shorten(node.get('status') or node.get('health') or node.get('freshness') or 'unknown', 12):12} "
            f"agent={shorten(node.get('agent_id') or '-', 24)}"
        )
        lines.append(f"  роль/возможности: {shorten(caps, 100)}")
        if node.get("active_task"):
            lines.append(f"  активная задача: {shorten(node.get('active_task'), 96)}")
    return "\n".join(lines)


def render_prs() -> str:
    queue = ROOT / "docs" / "agent" / "dispatcher" / "QUEUE.md"
    lines = [title("prs"), "GitHub/PR статус из dispatcher queue:"]
    for line in read_text(queue, MAX_LINES):
        if "PR" in line or "GitHub" in line or "merged" in line or "CI" in line or line.startswith("| P0 |"):
            lines.append(shorten(line, 150))
        if len(lines) >= MAX_LINES:
            break
    return "\n".join(lines)


def render_logs() -> str:
    paths = [
        ROOT / "docs" / "agent" / "dispatcher" / "DISPATCH_LOG.md",
        ROOT / "docs" / "agent" / "dispatcher" / "FACTORY_STATUS.md",
    ]
    lines = [title("logs"), "Последние безопасные записи из локальных журналов:"]
    for path in paths:
        lines.append(f"\n## {path.relative_to(ROOT)}")
        content = read_text(path, MAX_LINES)
        lines.extend(content[-18:])
    return "\n".join(lines[: MAX_LINES + 8])


def render_blockers() -> str:
    queue = ROOT / "docs" / "agent" / "dispatcher" / "QUEUE.md"
    lines = [title("blockers")]
    blockers = [
        line
        for line in read_text(queue, 220)
        if any(word in line.lower() for word in ("blocked", "failed", "dead_letter", "inactive", "stale", "требует", "blocker"))
    ]
    if not blockers:
        lines.append("Явные блокеры в dispatcher queue не найдены.")
    else:
        lines.extend(shorten(line, 150) for line in blockers[:MAX_LINES])
    return "\n".join(lines)


def render_owner() -> str:
    path = ROOT / "docs" / "agent" / "dispatcher" / "OWNER_CANONICAL_INSTRUCTIONS.md"
    lines = [title("owner"), "Видимые инструкции владельца:"]
    selected: list[str] = []
    for line in read_text(path, 180):
        if line.startswith("#") or line.startswith("- ") or line.startswith("Rule:") or "Owner" in line or "Владелец" in line or "Control Plane" in line:
            selected.append(line)
        if len(selected) >= MAX_LINES:
            break
    lines.extend(selected or read_text(path, MAX_LINES))
    return "\n".join(lines)


RENDERERS = {
    "overview": render_overview,
    "tasks": render_tasks,
    "agents": render_agents,
    "prs": render_prs,
    "logs": render_logs,
    "blockers": render_blockers,
    "owner": render_owner,
}


def loop_command(pane: str) -> str:
    return (
        "while true; do clear; "
        f"{subprocess.list2cmdline(['python3', str(ROOT / 'ops' / 'kolibri_home_screen.py'), 'pane', pane])}; "
        f"sleep {REFRESH_SECONDS}; done"
    )


def tmux_plan() -> list[list[str]]:
    return [
        ["tmux", "new-session", "-d", "-s", SESSION, "-n", "Фабрика", loop_command("overview")],
        ["tmux", "split-window", "-t", f"{SESSION}:0", "-h", loop_command("tasks")],
        ["tmux", "split-window", "-t", f"{SESSION}:0.0", "-v", loop_command("agents")],
        ["tmux", "split-window", "-t", f"{SESSION}:0.1", "-v", loop_command("prs")],
        ["tmux", "select-layout", "-t", f"{SESSION}:0", "tiled"],
        ["tmux", "new-window", "-t", SESSION, "-n", "События", loop_command("logs")],
        ["tmux", "split-window", "-t", f"{SESSION}:1", "-h", loop_command("blockers")],
        ["tmux", "new-window", "-t", SESSION, "-n", "Владелец", loop_command("owner")],
        ["tmux", "set-option", "-t", SESSION, "status-left", " Kolibri Home "],
        ["tmux", "set-option", "-t", SESSION, "status-right", " attach: tmux attach -t kolibri-factory-screen "],
    ]


def start_tmux(dry_run: bool = False) -> int:
    plan = [["tmux", "kill-session", "-t", SESSION]] + tmux_plan()
    for command in plan:
        if dry_run:
            print(subprocess.list2cmdline(command))
            continue
        if command[:2] == ["tmux", "kill-session"]:
            subprocess.run(command, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            continue
        subprocess.run(command, check=True)
    if not dry_run:
        print(f"kolibri_home_screen=started session={SESSION} attach='tmux attach -t {SESSION}'")
    return 0


def stop_tmux(dry_run: bool = False) -> int:
    command = ["tmux", "kill-session", "-t", SESSION]
    if dry_run:
        print(subprocess.list2cmdline(command))
        return 0
    subprocess.run(command, check=False)
    print(f"kolibri_home_screen=stopped session={SESSION}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Russian Kolibri Factory tmux/Home screen")
    sub = parser.add_subparsers(dest="command", required=True)
    pane = sub.add_parser("pane")
    pane.add_argument("name", choices=sorted(RENDERERS))
    sub.add_parser("start")
    sub.add_parser("stop")
    sub.add_parser("tmux-plan")
    args = parser.parse_args()

    if args.command == "pane":
        print(RENDERERS[args.name]())
        return 0
    if args.command == "start":
        return start_tmux()
    if args.command == "stop":
        return stop_tmux()
    if args.command == "tmux-plan":
        print("\n".join(subprocess.list2cmdline(cmd) for cmd in tmux_plan()))
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
