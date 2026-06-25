#!/usr/bin/env python3
"""Telegram long-polling gateway for the Kolibri Factory control plane."""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))
from orchestrator_roster import ORCHESTRATOR_CARD, node_card


STOP = False
SIGNIFICANT_STATES = {
    "queued": "QUEUED",
    "leased": "RUNNING",
    "running": "RUNNING",
    "waiting_review": "WAITING_REVIEW",
    "review": "RUNNING",
    "completed": "COMPLETED",
    "failed": "FAILED",
    "cancelled": "CANCELLED",
    "dead_letter": "FAILED",
}
TASK_INTENT_WORDS = {
    "исправь",
    "почини",
    "сделай",
    "добавь",
    "создай",
    "проверь",
    "запусти",
    "обнови",
    "измени",
    "убери",
    "настрой",
    "разверни",
    "deploy",
    "fix",
    "add",
    "create",
    "run",
    "update",
}
CHAT_GREETINGS = {
    "привет",
    "здравствуй",
    "здравствуйте",
    "добрый день",
    "доброе утро",
    "добрый вечер",
    "hello",
    "hi",
}
TERMINAL_TASK_STATES = {"completed", "failed", "cancelled", "dead_letter"}
OWNER_MESSAGE_FORBIDDEN_MARKERS = (
    "task_id",
    "node:",
    "agent:",
    "artifact:",
    "worktree",
    "result_path",
    "log_path",
    "/var/lib",
    "/tmp/",
    "TGCHAT-",
    "TG-202",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_owner_ids(value: str) -> set[int]:
    ids = set()
    for item in value.replace(";", ",").split(","):
        item = item.strip()
        if item:
            ids.add(int(item))
    return ids


def safe_task_suffix(text: str) -> str:
    allowed = []
    for ch in text.lower():
        if ch.isascii() and ch.isalnum():
            allowed.append(ch)
        elif ch in {" ", "-", "_"}:
            allowed.append("-")
    collapsed = "-".join(filter(None, "".join(allowed).split("-")))
    return (collapsed or "task")[:36]


def task_id_from_message(message: dict[str, Any]) -> str:
    suffix = safe_task_suffix(message.get("text", "task"))
    return f"TG-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{message['message_id']}-{suffix}"


def chat_task_id_from_message(message: dict[str, Any]) -> str:
    suffix = safe_task_suffix(message.get("text", "chat"))
    return f"TGCHAT-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{message['message_id']}-{suffix}"


def wants_factory_task(text: str) -> bool:
    lowered = text.strip().lower()
    if not lowered:
        return False
    if lowered in CHAT_GREETINGS:
        return False
    return any(word in lowered for word in TASK_INTENT_WORDS)


def json_request(method: str, url: str, body: dict[str, Any] | None = None, timeout: int = 35) -> Any:
    data = None
    headers = {"Content-Type": "application/json"}
    if body is not None:
        data = json.dumps(body, separators=(",", ":")).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 204:
                return None
            payload = resp.read().decode("utf-8")
            return json.loads(payload) if payload else None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"{method} {url} failed: HTTP {exc.code}: {detail}") from exc


class TelegramClient:
    def __init__(self, token: str, api_base: str = "https://api.telegram.org"):
        if not token:
            raise ValueError("Telegram token is required")
        self.api_base = api_base.rstrip("/")
        self.base_url = f"{self.api_base}/bot{token}"

    def call(self, method: str, payload: dict[str, Any] | None = None, timeout: int = 35) -> dict[str, Any]:
        data = urllib.parse.urlencode(payload or {}).encode("utf-8")
        req = urllib.request.Request(f"{self.base_url}/{method}", data=data, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            response = json.loads(resp.read().decode("utf-8"))
        if not response.get("ok"):
            raise RuntimeError(f"telegram {method} failed")
        return response

    def get_updates(self, offset: int | None, timeout: int) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {"timeout": timeout, "allowed_updates": json.dumps(["message"])}
        if offset is not None:
            payload["offset"] = offset
        return self.call("getUpdates", payload, timeout=timeout + 10).get("result", [])

    def send_message(self, chat_id: int, text: str) -> None:
        self.call("sendMessage", {"chat_id": chat_id, "text": text[:3900], "disable_web_page_preview": True})


class FactoryClient:
    def __init__(self, control_url: str):
        self.control_url = control_url.rstrip("/")

    def create_task(self, envelope: dict[str, Any]) -> dict[str, Any]:
        return json_request("POST", f"{self.control_url}/v1/tasks", envelope)

    def get_task(self, task_id: str) -> dict[str, Any]:
        return json_request("GET", f"{self.control_url}/v1/tasks/{urllib.parse.quote(task_id, safe='')}")

    def get_tasks(self) -> dict[str, Any]:
        return json_request("GET", f"{self.control_url}/v1/tasks")

    def cancel_task(self, task_id: str) -> dict[str, Any]:
        quoted = urllib.parse.quote(task_id, safe="")
        return json_request("POST", f"{self.control_url}/v1/tasks/{quoted}/cancel", {"reason": "telegram cancel"})

    def nodes(self) -> dict[str, Any]:
        return json_request("GET", f"{self.control_url}/v1/nodes")


def compact_factory_snapshot(factory: FactoryClient) -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "captured_at": utc_now(),
        "orchestrator": ORCHESTRATOR_CARD,
        "team": [],
        "nodes": [],
        "task_counts": {},
        "queue_length": 0,
        "active_tasks": [],
        "warnings": [],
    }
    try:
        nodes = factory.nodes().get("nodes", [])
        snapshot["nodes"] = [
            {
                "node_id": node.get("node_id"),
                "health": node.get("health"),
                "capabilities": node.get("capabilities", []),
                "draining": bool(node.get("draining")),
                "heartbeat_at": node.get("heartbeat_at"),
            }
            for node in nodes
        ]
        snapshot["team"] = [node_card(node) for node in nodes]
    except Exception as exc:
        snapshot["warnings"].append(f"nodes_unavailable:{type(exc).__name__}")
    try:
        payload = factory.get_tasks()
        tasks = payload.get("tasks", [])
        snapshot["queue_length"] = len(payload.get("queue", []))
        counts: dict[str, int] = {}
        active = []
        for task in tasks:
            state = str(task.get("state") or "unknown")
            counts[state] = counts.get(state, 0) + 1
            if state not in TERMINAL_TASK_STATES:
                envelope = task.get("envelope") or {}
                active.append({
                    "state": state,
                    "kind": task.get("kind") or envelope.get("kind"),
                    "target_node": envelope.get("target_node"),
                    "review_node": envelope.get("review_node"),
                })
        snapshot["task_counts"] = counts
        snapshot["active_tasks"] = active[:8]
    except Exception as exc:
        snapshot["warnings"].append(f"tasks_unavailable:{type(exc).__name__}")
    return snapshot


def build_task_envelope(message: dict[str, Any], text: str) -> dict[str, Any]:
    task_id = task_id_from_message(message)
    branch_slug = safe_task_suffix(text)
    return {
        "task_id": task_id,
        "idempotency_key": f"telegram:{message['chat']['id']}:{message['message_id']}",
        "kind": "impl_retry_error_clearance",
        "target_node": "9fts",
        "required_capability": "implementation",
        "review_node": "new",
        "create_review_on_complete": True,
        "branch": f"agent/{task_id}/impl/{branch_slug}",
        "base_branch": "main",
        "base_ref": "origin/main",
        "max_retries": 3,
        "objective": text,
        "source": {
            "kind": "telegram",
            "message_id": message["message_id"],
            "chat_id": message["chat"]["id"],
            "user_id": message["from"]["id"],
            "accepted_at": utc_now(),
        },
    }


def build_chat_envelope(message: dict[str, Any], text: str, snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    task_id = chat_task_id_from_message(message)
    return {
        "task_id": task_id,
        "idempotency_key": f"telegram-chat:{message['chat']['id']}:{message['message_id']}",
        "kind": "orchestrator_chat_response",
        "target_node": "9fts",
        "required_capability": "implementation",
        "max_retries": 1,
        "message": text,
        "factory_snapshot": snapshot or {},
        "source": {
            "kind": "telegram",
            "message_id": message["message_id"],
            "chat_id": message["chat"]["id"],
            "user_id": message["from"]["id"],
            "accepted_at": utc_now(),
        },
    }


def help_text() -> str:
    return (
        "Kolibri Factory\n"
        "/task <текст>\n"
        "/status <task_id>\n"
        "/cancel <task_id>\n"
        "/retry <task_id>\n"
        "/nodes\n"
        "/agents\n"
        "/queue\n"
        "/help"
    )


class StateStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self.load()

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"offset": None, "tracked": {}}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self) -> None:
        self.path.write_text(json.dumps(self.data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class Gateway:
    def __init__(self, telegram: TelegramClient, factory: FactoryClient, owner_ids: set[int], state: StateStore, poll_timeout: int):
        self.telegram = telegram
        self.factory = factory
        self.owner_ids = owner_ids
        self.state = state
        self.poll_timeout = poll_timeout

    def authorized(self, message: dict[str, Any]) -> bool:
        user = message.get("from") or {}
        chat = message.get("chat") or {}
        return chat.get("type") == "private" and int(user.get("id", 0)) in self.owner_ids

    def reject(self, message: dict[str, Any]) -> None:
        chat_id = message.get("chat", {}).get("id")
        if chat_id:
            self.telegram.send_message(chat_id, "Доступ запрещен.")

    def track(self, chat_id: int, task_id: str, state: str, mode: str = "task") -> None:
        self.state.data.setdefault("tracked", {})[task_id] = {"chat_id": chat_id, "last_state": state, "mode": mode}
        self.state.save()

    def submit_text_task(self, message: dict[str, Any], text: str) -> None:
        envelope = build_task_envelope(message, text)
        task = self.factory.create_task(envelope)
        self.track(message["chat"]["id"], task["task_id"], task["state"])
        self.telegram.send_message(
            message["chat"]["id"],
            "Принял задачу в работу. Я сам выберу подходящего исполнителя и вернусь с важным результатом.",
        )

    def submit_chat_task(self, message: dict[str, Any], text: str) -> None:
        envelope = build_chat_envelope(message, text, compact_factory_snapshot(self.factory))
        task = self.factory.create_task(envelope)
        self.track(message["chat"]["id"], task["task_id"], task["state"], mode="chat")
        self.telegram.send_message(
            message["chat"]["id"],
            "Я здесь. Смотрю контекст фабрики и отвечаю.",
        )

    def handle_command(self, message: dict[str, Any], text: str) -> None:
        chat_id = message["chat"]["id"]
        command, _, arg = text.partition(" ")
        command = command.split("@", 1)[0]
        arg = arg.strip()
        if command in {"/start", "/help"}:
            self.telegram.send_message(chat_id, help_text())
        elif command == "/task" and arg:
            self.submit_text_task(message, arg)
        elif command == "/status" and arg:
            task = self.factory.get_task(arg)
            self.telegram.send_message(chat_id, format_task_status(task))
        elif command == "/cancel" and arg:
            task = self.factory.cancel_task(arg)
            self.telegram.send_message(chat_id, format_task_status(task))
        elif command == "/retry" and arg:
            old = self.factory.get_task(arg)
            envelope = dict(old.get("envelope") or {})
            envelope["task_id"] = f"{arg}-RETRY-{int(time.time())}"
            envelope["idempotency_key"] = f"retry:{arg}:{int(time.time())}"
            task = self.factory.create_task(envelope)
            self.track(chat_id, task["task_id"], task["state"])
            self.telegram.send_message(chat_id, format_task_status(task))
        elif command == "/nodes":
            nodes = self.factory.nodes().get("nodes", [])
            self.telegram.send_message(chat_id, "\n".join(format_node(node) for node in nodes) or "nodes: empty")
        elif command == "/agents":
            nodes = self.factory.nodes().get("nodes", [])
            self.telegram.send_message(chat_id, "\n".join(f"{n.get('node_id')}: {n.get('agent_id')} pid={n.get('pid')} health={n.get('health')}" for n in nodes) or "agents: empty")
        elif command == "/queue":
            tasks = self.factory.get_tasks()
            self.telegram.send_message(chat_id, f"queue: {len(tasks.get('queue', []))}\n" + "\n".join(tasks.get("queue", [])))
        else:
            self.telegram.send_message(chat_id, help_text())

    def handle_message(self, message: dict[str, Any]) -> None:
        if not self.authorized(message):
            self.reject(message)
            return
        text = (message.get("text") or "").strip()
        if not text:
            return
        if text.startswith("/"):
            self.handle_command(message, text)
        elif wants_factory_task(text):
            self.submit_text_task(message, text)
        else:
            self.submit_chat_task(message, text)

    def poll_task_transitions(self) -> None:
        tracked = dict(self.state.data.get("tracked", {}))
        for task_id, record in tracked.items():
            task = self.factory.get_task(task_id)
            state = task.get("state")
            label = SIGNIFICANT_STATES.get(state)
            if label and label != record.get("last_state"):
                mode = record.get("mode", "task")
                self.telegram.send_message(int(record["chat_id"]), format_transition(label, task, mode))
                self.state.data["tracked"][task_id]["last_state"] = label
                self.state.save()

    def run_once(self) -> None:
        updates = self.telegram.get_updates(self.state.data.get("offset"), self.poll_timeout)
        for update in updates:
            self.state.data["offset"] = int(update["update_id"]) + 1
            message = update.get("message")
            if message:
                self.handle_message(message)
        self.state.save()
        self.poll_task_transitions()

    def run(self) -> None:
        while not STOP:
            try:
                self.run_once()
            except Exception as exc:  # pragma: no cover - surfaced in systemd logs
                print(json.dumps({"event": "telegram_gateway_error", "error": str(exc), "time": utc_now()}), file=sys.stderr)
                time.sleep(5)


def format_node(node: dict[str, Any]) -> str:
    card = node_card(node)
    return f"{card['name']} — {card['role']}\nСостояние: {card['health']}\nЗадача: {card['responsibility']}"


def human_task_state(state: str | None) -> str:
    return {
        "queued": "Задача в очереди.",
        "leased": "Удаленный исполнитель начал работу.",
        "running": "Удаленный исполнитель работает.",
        "waiting_review": "Изменение готово и передано на независимую проверку.",
        "review": "Идет независимая проверка.",
        "completed": "Готово. Я проверяю результат и следующий безопасный шаг.",
        "failed": "Есть технический сбой. Я зафиксировал его и продолжу разбор.",
        "cancelled": "Задача отменена.",
        "dead_letter": "Есть технический сбой. Я зафиксировал его и продолжу разбор.",
    }.get(state or "", "Статус обновился.")


def format_task_status(task: dict[str, Any]) -> str:
    result = task.get("result") or {}
    lines = [human_task_state(task.get("state"))]
    pr_url = result.get("pull_request_url") or result.get("pr_url")
    if pr_url:
        lines.append(f"PR готов: {pr_url}")
    return "\n".join(lines)


def clean_agent_response(text: str | None) -> str:
    clean_chars = []
    for ch in text or "":
        if unicodedata.category(ch) in {"So", "Sk"}:
            continue
        clean_chars.append(ch)
    lines = []
    for line in "".join(clean_chars).splitlines():
        stripped = " ".join(line.strip().split())
        lowered = stripped.lower()
        if any(marker.lower() in lowered for marker in OWNER_MESSAGE_FORBIDDEN_MARKERS):
            continue
        if stripped:
            lines.append(stripped)
    cleaned = "\n".join(lines).strip()
    return cleaned or "Я завершил ответ, но текст не записался. Разберу это отдельно."


def format_transition(label: str, task: dict[str, Any], mode: str = "task") -> str:
    result = task.get("result") or {}
    if mode == "chat" and label == "COMPLETED":
        return clean_agent_response(result.get("response"))
    if mode == "chat" and label == "FAILED":
        return "Сейчас не смог подготовить ответ. Я зафиксировал сбой и продолжу восстановление."
    return format_task_status(task)


def handle_stop(signum: int, frame: Any) -> None:
    del signum, frame
    global STOP
    STOP = True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--control-url", default=os.environ.get("KOLIBRI_FACTORY_CONTROL_URL", "http://10.99.0.2:9101"))
    parser.add_argument("--state-file", default=os.environ.get("TELEGRAM_GATEWAY_STATE", "/var/lib/kolibri-telegram-gateway/state.json"))
    parser.add_argument("--poll-timeout", type=int, default=int(os.environ.get("TELEGRAM_POLL_TIMEOUT", "25")))
    args = parser.parse_args()
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    owner_ids = parse_owner_ids(os.environ.get("TELEGRAM_OWNER_IDS", ""))
    if not owner_ids:
        raise SystemExit("TELEGRAM_OWNER_IDS is required")
    signal.signal(signal.SIGTERM, handle_stop)
    signal.signal(signal.SIGINT, handle_stop)
    gateway = Gateway(TelegramClient(token), FactoryClient(args.control_url), owner_ids, StateStore(Path(args.state_file)), args.poll_timeout)
    gateway.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
