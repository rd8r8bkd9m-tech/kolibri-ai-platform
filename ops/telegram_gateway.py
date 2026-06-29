#!/usr/bin/env python3
"""Telegram long-polling gateway for the Kolibri Factory control plane."""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import re
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
from orchestrator_memory import (
    empty_memory,
    ensure_memory,
    memory_snapshot,
    record_orchestrator_message,
    record_owner_message,
    record_task_transition,
    record_work_task,
)


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
IMAGE_INTENT_WORDS = (
    "нарисуй",
    "рисуй",
    "сгенерируй картинку",
    "сгенерируй изображение",
    "сделай картинку",
    "сделай изображение",
    "создай картинку",
    "создай изображение",
    "картинку",
    "картинка",
    "изображение",
    "иллюстрацию",
    "иллюстрация",
    "лого",
    "логотип",
    "маскот",
    "птичку",
    "image",
    "picture",
    "generate image",
    "draw",
)
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
    "secret",
    "token",
    "_key",
    "env_file",
    "сами значения",
)
OWNER_RESPONSE_REPLACEMENTS = {
    "Kolibi": "Kolibri",
    "kolibi": "Kolibri",
    "Колиби": "Колибри",
    "колиби": "Колибри",
}
OWNER_RUNTIME_FAILURE_MARKERS = (
    "command failed",
    "run --format",
    "telegram-chat-",
    "tgchat-",
    "rc=",
    "traceback",
    "runtimeerror",
    "--title",
    "ты — центральный оркестратор",
)
IMMEDIATE_CHAT_MARKERS = (
    "как дела",
    "как ты",
    "что нового",
    "как зовут",
    "тебя зовут",
    "кто ты",
    "статус",
    "что делаешь",
    "какие задачи",
    "контекст",
    "помнишь",
    "память",
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


def iso_timestamp(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


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


def image_task_id_from_message(message: dict[str, Any]) -> str:
    suffix = safe_task_suffix(message.get("text", "image"))
    return f"TGIMG-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{message['message_id']}-{suffix}"


def wants_image_generation(text: str) -> bool:
    lowered = text.strip().lower()
    if not lowered:
        return False
    return any(marker in lowered for marker in IMAGE_INTENT_WORDS)


def wants_factory_task(text: str) -> bool:
    lowered = text.strip().lower()
    if not lowered:
        return False
    if lowered in CHAT_GREETINGS:
        return False
    if any(word in lowered for word in TASK_INTENT_WORDS):
        return True
    task_targets = (
        "telegram", "телеграм", "miniapp", "миниапп", "webapp", "веб",
        "прилож", "сайт", "сервер", "agent", "агент", "pdf", "пдф",
        "смет", "документ", "vpn", "впн", "сеть", "primary", "примари",
        "frontend", "backend", "фронтенд", "бэкенд",
    )
    priority_words = ("p0", "p1", "срочно", "приоритет")
    if any(word in lowered for word in priority_words) and any(target in lowered for target in task_targets):
        return True
    if "?" in lowered:
        return False
    return any(target in lowered for target in task_targets) and len(lowered.split()) <= 6


def should_answer_immediately(text: str) -> bool:
    lowered = text.strip().lower()
    if not lowered:
        return False
    if answer_simple_arithmetic(text) is not None and os.environ.get("TELEGRAM_DETERMINISTIC_SHORTCUTS", "0") == "1":
        return True
    return False


def owner_safe_runtime_failure(text: str, snapshot: dict[str, Any] | None = None) -> str:
    del text
    active = len((snapshot or {}).get("active_tasks") or [])
    if active:
        return "Внутри фабрики упал исполнитель. Я не буду выносить технический мусор в чат: зафиксировал сбой и переключаю разбор на рабочий контур."
    return "Внутри фабрики упал исполнитель. Я зафиксировал сбой и разберу его отдельно; в чат дальше будут приходить только нормальные ответы."


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

    def call_multipart(
        self,
        method: str,
        fields: dict[str, Any],
        files: dict[str, tuple[str, bytes, str]],
        timeout: int = 60,
    ) -> dict[str, Any]:
        boundary = f"kolibri-{int(time.time() * 1000)}"
        chunks: list[bytes] = []
        for name, value in fields.items():
            if value is None:
                continue
            chunks.append(f"--{boundary}\r\n".encode("utf-8"))
            chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
            chunks.append(str(value).encode("utf-8"))
            chunks.append(b"\r\n")
        for name, (filename, content, content_type) in files.items():
            chunks.append(f"--{boundary}\r\n".encode("utf-8"))
            chunks.append(
                (
                    f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
                    f"Content-Type: {content_type}\r\n\r\n"
                ).encode("utf-8")
            )
            chunks.append(content)
            chunks.append(b"\r\n")
        chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
        data = b"".join(chunks)
        req = urllib.request.Request(
            f"{self.base_url}/{method}",
            data=data,
            method="POST",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "Content-Length": str(len(data))},
        )
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

    def send_message(self, chat_id: int, text: str) -> dict[str, Any]:
        response = self.call("sendMessage", {"chat_id": chat_id, "text": text[:3900], "disable_web_page_preview": True})
        return response.get("result") or {}

    def send_photo(self, chat_id: int, photo: str | bytes | Path, caption: str | None = None, mime_type: str | None = None) -> dict[str, Any]:
        fields: dict[str, Any] = {"chat_id": chat_id}
        if caption:
            fields["caption"] = caption[:1024]
        if isinstance(photo, bytes):
            content_type = mime_type or "image/png"
            response = self.call_multipart(
                "sendPhoto",
                fields,
                {"photo": ("image.png", photo, content_type)},
            )
            return response.get("result") or {}
        if isinstance(photo, Path):
            content = photo.read_bytes()
            content_type = mime_type or mimetypes.guess_type(photo.name)[0] or "application/octet-stream"
            response = self.call_multipart(
                "sendPhoto",
                fields,
                {"photo": (photo.name, content, content_type)},
            )
            return response.get("result") or {}
        fields["photo"] = photo
        response = self.call("sendPhoto", fields, timeout=60)
        return response.get("result") or {}

    def edit_message(self, chat_id: int, message_id: int, text: str) -> dict[str, Any]:
        response = self.call(
            "editMessageText",
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text[:3900],
                "disable_web_page_preview": True,
            },
        )
        return response.get("result") or {}

    def send_action(self, chat_id: int, action: str = "typing") -> None:
        self.call("sendChatAction", {"chat_id": chat_id, "action": action}, timeout=10)


class FactoryClient:
    def __init__(self, control_url: str, control_urls: str | None = None):
        urls = [url.strip().rstrip("/") for url in (control_urls or control_url).split(",") if url.strip()]
        self.control_urls = urls or [control_url.rstrip("/")]
        self.control_url = self.control_urls[0]

    def ordered_control_urls(self) -> list[str]:
        urls = [self.control_url]
        urls.extend(url for url in self.control_urls if url != self.control_url)
        return urls

    def request(self, method: str, path: str, body: dict[str, Any] | None = None, timeout: int = 35) -> Any:
        last_exc: Exception | None = None
        for control_url in self.ordered_control_urls():
            try:
                result = json_request(method, f"{control_url}{path}", body, timeout=timeout)
                self.control_url = control_url
                return result
            except Exception as exc:
                last_exc = exc
        assert last_exc is not None
        raise last_exc

    def create_task(self, envelope: dict[str, Any]) -> dict[str, Any]:
        return self.request("POST", "/v1/tasks", envelope)

    def get_task(self, task_id: str) -> dict[str, Any]:
        return self.request("GET", f"/v1/tasks/{urllib.parse.quote(task_id, safe='')}")

    def get_tasks(self) -> dict[str, Any]:
        return self.request("GET", "/v1/tasks")

    def cancel_task(self, task_id: str) -> dict[str, Any]:
        quoted = urllib.parse.quote(task_id, safe="")
        return self.request("POST", f"/v1/tasks/{quoted}/cancel", {"reason": "telegram cancel"})

    def nodes(self) -> dict[str, Any]:
        return self.request("GET", "/v1/nodes")


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


def build_task_envelope(message: dict[str, Any], text: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    task_id = task_id_from_message(message)
    branch_slug = safe_task_suffix(text)
    project_path = os.environ.get("TELEGRAM_OWNER_PROJECT_PATH")
    lowered = text.lower()
    if not project_path and ("kimi" in lowered or "кими" in lowered or "колибрифин" in lowered):
        project_path = "/home/ladik/kolibri-projects/kimi_agent_kolibrifin"
    envelope = {
        "task_id": task_id,
        "idempotency_key": f"telegram:{message['chat']['id']}:{message['message_id']}",
        "kind": os.environ.get("TELEGRAM_TASK_KIND", "owner_remote_task"),
        "required_capability": os.environ.get("TELEGRAM_TASK_CAPABILITY", "generic_implementation"),
        "review_node": "new",
        "create_review_on_complete": False,
        "branch": f"agent/{task_id}/impl/{branch_slug}",
        "base_branch": "main",
        "base_ref": "origin/main",
        "max_retries": int(os.environ.get("TELEGRAM_TASK_MAX_RETRIES", "1")),
        "objective": text,
        "project_path": project_path,
        "conversation_context": context or {},
        "source": {
            "kind": "telegram",
            "message_id": message["message_id"],
            "chat_id": message["chat"]["id"],
            "user_id": message["from"]["id"],
            "accepted_at": utc_now(),
        },
    }
    if os.environ.get("TELEGRAM_HOME_SCREEN_AGENT", "").strip().lower() in {"1", "true", "yes", "on"}:
        envelope["target_node"] = os.environ.get("TELEGRAM_HOME_SCREEN_NODE", "home-live")
        envelope["runner"] = os.environ.get("TELEGRAM_HOME_SCREEN_RUNNER", "mimo")
        envelope["visible_on_screen"] = True
        envelope["screen_agent"] = True
    target_node = os.environ.get("TELEGRAM_TASK_NODE")
    if target_node:
        envelope["target_node"] = target_node
    if os.environ.get("TELEGRAM_TASK_VISIBLE_ON_SCREEN", "").strip().lower() in {"1", "true", "yes", "on"}:
        envelope["visible_on_screen"] = True
        envelope["screen_agent"] = True
        envelope["runner"] = os.environ.get("TELEGRAM_TASK_RUNNER", envelope.get("runner", "mimo"))
    return envelope


def build_chat_envelope(message: dict[str, Any], text: str, snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    task_id = chat_task_id_from_message(message)
    context = snapshot or {}
    objective = (
        "Сгенерируй живой короткий ответ владельцу проекта в Telegram. "
        "Отвечай как директор-оркестратор проекта: естественно, по-русски, без заготовок, без markdown, "
        "без task_id, node, agent, путей, команд и служебных деталей. "
        "Не называй себя брендом продукта. Если владелец просто здоровается, ответь по-человечески и мягко, "
        "но не используй заранее заданную фразу. Если владелец спрашивает о работе, используй контекст фабрики. "
        f"Контекст фабрики: {json.dumps(context, ensure_ascii=False, sort_keys=True)}\n"
        f"Сообщение владельца: {text}"
    )
    envelope = {
        "task_id": task_id,
        "idempotency_key": f"telegram-chat:{message['chat']['id']}:{message['message_id']}",
        "kind": os.environ.get("TELEGRAM_CHAT_KIND", "owner_remote_task"),
        "required_capability": os.environ.get("TELEGRAM_CHAT_CAPABILITY", "generic_implementation"),
        "max_retries": 1,
        "message": text,
        "objective": objective,
        "runner": os.environ.get("TELEGRAM_CHAT_RUNNER", "codex"),
        "factory_snapshot": context,
        "source": {
            "kind": "telegram",
            "message_id": message["message_id"],
            "chat_id": message["chat"]["id"],
            "user_id": message["from"]["id"],
            "accepted_at": utc_now(),
        },
    }
    target_node = os.environ.get("TELEGRAM_CHAT_NODE", "primary-candidate")
    if target_node:
        envelope["target_node"] = target_node
    return envelope


def build_image_envelope(message: dict[str, Any], text: str, snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    task_id = image_task_id_from_message(message)
    context = snapshot or {}
    prompt = (
        "Сгенерируй изображение по запросу владельца. "
        "Нужно вернуть структурированный результат для Telegram: image_url или image_b64/image_path, "
        "image_mime_type и короткую подпись caption по-русски. "
        "Не раскрывай секреты, пути, task_id, node, agent и служебные детали владельцу. "
        f"Контекст фабрики: {json.dumps(context, ensure_ascii=False, sort_keys=True)}\n"
        f"Запрос владельца: {text}"
    )
    envelope = {
        "task_id": task_id,
        "idempotency_key": f"telegram-image:{message['chat']['id']}:{message['message_id']}",
        "kind": os.environ.get("TELEGRAM_IMAGE_KIND", "telegram_image_generation"),
        "required_capability": os.environ.get("TELEGRAM_IMAGE_CAPABILITY", "generic_implementation"),
        "max_retries": int(os.environ.get("TELEGRAM_IMAGE_MAX_RETRIES", "1")),
        "message": text,
        "prompt": text,
        "objective": prompt,
        "runner": os.environ.get("TELEGRAM_IMAGE_RUNNER", "image"),
        "factory_snapshot": context,
        "source": {
            "kind": "telegram",
            "message_id": message["message_id"],
            "chat_id": message["chat"]["id"],
            "user_id": message["from"]["id"],
            "accepted_at": utc_now(),
        },
    }
    target_node = os.environ.get("TELEGRAM_IMAGE_NODE", os.environ.get("TELEGRAM_CHAT_NODE", "primary-candidate"))
    if target_node:
        envelope["target_node"] = target_node
    return envelope


def has_any(text: str, words: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in words)


def answer_simple_arithmetic(text: str) -> str | None:
    expression = text.strip().replace(",", ".")
    if not re.fullmatch(r"[0-9\s+\-*/().]+", expression):
        return None
    if not re.search(r"[+\-*/]", expression):
        return None
    try:
        value = eval(expression, {"__builtins__": {}}, {})
    except Exception:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value)


def describe_task_state(state: str | None) -> str:
    return {
        "queued": "в очереди",
        "leased": "назначена исполнителю",
        "running": "в работе",
        "waiting_review": "ожидает независимую проверку",
        "review": "на независимой проверке",
        "completed": "готова",
        "failed": "требует моего разбора",
        "dead_letter": "требует моего разбора",
        "cancelled": "отменена",
    }.get(state or "", "под контролем")


def summarize_team(snapshot: dict[str, Any]) -> str:
    team = snapshot.get("team") or []
    online = [member.get("name") for member in team if member.get("health") == "online" and member.get("name")]
    if online:
        return ", ".join(online[:4])
    nodes = snapshot.get("nodes") or []
    online_nodes = [node.get("node_id") for node in nodes if node.get("health") == "online" and node.get("node_id")]
    return ", ".join(online_nodes[:4]) or "состав уточняю"


def last_work_line(memory: dict[str, Any]) -> str:
    last = memory.get("last_work_request") or {}
    text = (last.get("text") or "").strip()
    state = describe_task_state(last.get("state"))
    if text:
        return f"Последняя задача: {text}. Сейчас она {state}."
    return "Последней рабочей задачи в памяти пока нет."


def first_known_url(memory: dict[str, Any]) -> str | None:
    for item in reversed(memory.get("known_results") or []):
        url = item.get("url")
        if url:
            return str(url)
    return None


def build_realtime_owner_reply(text: str, snapshot: dict[str, Any]) -> str:
    memory = snapshot.get("memory") or {}
    lowered = text.lower().strip()
    active_tasks = snapshot.get("active_tasks") or []
    team = summarize_team(snapshot)
    last = memory.get("last_work_request") or {}
    last_text = (last.get("text") or "").strip()
    last_state = last.get("state")
    last_state_text = describe_task_state(last_state)
    url = first_known_url(memory)

    arithmetic = answer_simple_arithmetic(text)
    if arithmetic is not None:
        return arithmetic

    if has_any(text, ("как дела", "как ты", "что нового")):
        if active_tasks:
            return f"Работа идёт. Сейчас вижу активные задачи и держу команду в фокусе: {team}."
        return f"Я в порядке и смотрю на контур. Активных задач прямо сейчас не вижу, команда доступна: {team}."

    if has_any(text, ("как зовут", "тебя зовут", "кто ты")):
        return "Для проекта я директор-оркестратор. Можешь обращаться ко мне просто как к Директору: я принимаю задачи, распределяю работу и возвращаю понятный результат."

    if has_any(text, ("ссыл", "url", "линк", "link")):
        if url:
            return f"Да, помню. Вот ссылка: {url}"
        if last_text:
            return f"Помню про задачу: {last_text}. Ссылку пришлю, когда появится рабочий preview или staging. Сейчас задача {last_state_text}."
        return "Помню, что нужна ссылка. Готового preview или staging URL пока нет, я держу это ожидание открытым."

    asks_running_result = has_any(text, ("запущ", "работает", "готов", "дев", "dev", "сервер", "preview", "веб"))
    if asks_running_result and (url or last_text):
        if url and last_state == "completed":
            return f"Да, запущено. Веб-приложение доступно здесь: {url}"
        if url:
            return f"Есть рабочая ссылка: {url}. По последней задаче статус: {last_state_text}."
        return f"По последней задаче: {last_text}. Сейчас она {last_state_text}."

    if has_any(text, ("что делаешь", "какие задачи", "статус", "что сделано", "не завис", "монитор", "кто делает", "что выполня")):
        if active_tasks:
            task_count = len(active_tasks)
            prefix = f"Сейчас в работе {task_count} задач."
        else:
            prefix = "Сейчас активных задач не вижу."
        if url and last_state == "completed":
            return f"{prefix} Последний результат готов: {url}"
        return f"{prefix} Команда на связи: {team}. {last_work_line(memory)}"

    if has_any(text, ("контекст", "помнишь", "память", "знаешь")):
        if url:
            return f"Да, контекст держу на удаленном сервере. Помню последний результат: {url}"
        return f"Да, контекст держу на удаленном сервере. {last_work_line(memory)}"

    if "?" in text:
        if url and last_state == "completed":
            return f"Да. Последний готовый результат здесь: {url}"
        return f"Отвечаю сразу. Команда на связи: {team}. {last_work_line(memory)}"

    return f"Слышу. Продолжаю из текущего контекста: {last_work_line(memory)}"


def build_task_ack_reply(text: str, snapshot: dict[str, Any], task: dict[str, Any]) -> str:
    del task
    active = len(snapshot.get("active_tasks") or [])
    lowered = text.lower()
    if has_any(lowered, ("telegram", "телеграм", "бот", "mini app", "миниапп")):
        return "Да, это главный баг интерфейса. Забираю его как P0: чиню живой Telegram-диалог, контекст и поток обновлений от директора."
    if has_any(lowered, ("mesh", "мэш", "единый компьютер", "единый организм", "синхронизац")):
        return "Беру в работу контур связи. Цель понятна: фабрика должна общаться через mesh/API и видеть общий контекст, а не жить отдельными серверами."
    if has_any(lowered, ("деплой", "deploy", "запусти", "дев", "dev", "ссыл")):
        return "Задачу принял. Отдам исполнителю через фабрику и верну рабочую ссылку только после реальной проверки."
    if active:
        return f"Принял задачу. Вижу ещё {active} активных процессов, поэтому поставлю её в очередь без потери контекста и буду вести результат здесь."
    return "Принял задачу. Сам назначу исполнителя и буду возвращать сюда только понятные статусы и результат."


def help_text() -> str:
    return (
        "Пишите обычным языком. Я отвечаю сам, держу контекст разработки и сам решаю, "
        "когда это разговор, а когда задача для фабрики."
    )


class StateStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self.load()

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            data = {"offset": None, "tracked": {}, "memory": empty_memory()}
        else:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        data.setdefault("offset", None)
        data.setdefault("tracked", {})
        data.setdefault("common_chat_since", os.environ.get("TELEGRAM_COMMON_CHAT_SINCE", utc_now()))
        ensure_memory(data)
        return data

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

    def owner_chat_id(self) -> int | None:
        chat_id = self.state.data.get("owner_chat_id")
        if chat_id:
            return int(chat_id)
        for record in (self.state.data.get("tracked") or {}).values():
            if record.get("chat_id"):
                return int(record["chat_id"])
        return None

    def memory(self) -> dict[str, Any]:
        return ensure_memory(self.state.data)

    def conversation_snapshot(self) -> dict[str, Any]:
        snapshot = compact_factory_snapshot(self.factory)
        snapshot["memory"] = memory_snapshot(self.memory())
        return snapshot

    def remember_owner_message(self, text: str, intent: str) -> None:
        record_owner_message(self.memory(), text, intent, utc_now())
        self.state.save()

    def remember_orchestrator_message(self, text: str) -> None:
        record_orchestrator_message(self.memory(), text, utc_now())
        self.state.save()

    def send_stream_update(self, chat_id: int, message_id: int | None, text: str) -> int | None:
        text = text.strip()
        if not text:
            return message_id
        if message_id and hasattr(self.telegram, "edit_message"):
            try:
                self.telegram.edit_message(chat_id, message_id, text)
                return message_id
            except Exception:
                pass
        sent = self.telegram.send_message(chat_id, text)
        if isinstance(sent, dict) and sent.get("message_id"):
            return int(sent["message_id"])
        return message_id

    def send_image_result(self, chat_id: int, task: dict[str, Any]) -> str:
        delivery = image_delivery_from_task(task)
        caption = clean_image_caption(delivery.get("caption"))
        photo = delivery.get("photo")
        mime_type = delivery.get("mime_type")
        if isinstance(photo, str) and photo.startswith("/"):
            photo_obj: str | bytes | Path = Path(photo)
        else:
            photo_obj = photo
        if not photo_obj:
            raise RuntimeError("image task completed without deliverable image")
        self.telegram.send_photo(chat_id, photo_obj, caption=caption, mime_type=mime_type)
        return caption or "Готово, отправил изображение."

    def submit_text_task(self, message: dict[str, Any], text: str) -> None:
        snapshot = self.conversation_snapshot()
        envelope = build_task_envelope(message, text, snapshot)
        try:
            task = self.factory.create_task(envelope)
        except Exception:
            record_work_task(self.memory(), text, envelope["task_id"], "failed", utc_now())
            self.state.save()
            reply = "Я услышал задачу, но Control Plane сейчас не принял её в очередь. Зафиксировал сбой и разбираю отдельно."
            self.telegram.send_message(message["chat"]["id"], reply)
            self.remember_orchestrator_message(reply)
            return
        self.track(message["chat"]["id"], task["task_id"], task["state"])
        record_work_task(self.memory(), text, task["task_id"], task["state"], utc_now())
        self.state.save()
        reply = build_task_ack_reply(text, snapshot, task)
        self.telegram.send_message(message["chat"]["id"], reply)
        self.remember_orchestrator_message(reply)

    def submit_image_task(self, message: dict[str, Any], text: str) -> None:
        chat_id = message["chat"]["id"]
        snapshot = self.conversation_snapshot()
        envelope = build_image_envelope(message, text, snapshot)
        try:
            task = self.factory.create_task(envelope)
        except Exception:
            record_work_task(self.memory(), text, envelope["task_id"], "failed", utc_now())
            self.state.save()
            reply = "Я понял запрос на изображение, но фабрика сейчас не приняла задачу. Зафиксировал сбой и разберу отдельно."
            self.telegram.send_message(chat_id, reply)
            self.remember_orchestrator_message(reply)
            return
        self.track(chat_id, task["task_id"], task["state"], mode="image")
        record_work_task(self.memory(), text, task["task_id"], task["state"], utc_now())
        self.state.save()
        reply = "Принял. Запускаю генерацию изображения и пришлю сюда готовую картинку."
        self.telegram.send_message(chat_id, reply)
        self.remember_orchestrator_message(reply)

    def submit_chat_task(self, message: dict[str, Any], text: str) -> None:
        chat_id = message["chat"]["id"]
        snapshot = self.conversation_snapshot()
        task = self.factory.create_task(build_chat_envelope(message, text, snapshot))
        initial_label = SIGNIFICANT_STATES.get(task.get("state"), task.get("state"))
        self.track(chat_id, task["task_id"], initial_label or "queued", mode="chat")

        wait_seconds = int(os.environ.get("TELEGRAM_CHAT_WAIT_SECONDS", "90"))
        first_reply_seconds = int(os.environ.get("TELEGRAM_CHAT_FIRST_REPLY_SECONDS", "0"))
        deadline = time.time() + max(0, wait_seconds)
        first_reply_at = time.time() + max(0, first_reply_seconds) if first_reply_seconds > 0 else None
        last_action = 0.0
        last_sent = ""
        stream_message_id: int | None = None
        while time.time() < deadline:
            now = time.time()
            if now - last_action >= 4:
                self.telegram.send_action(chat_id)
                last_action = now
            current = self.factory.get_task(task["task_id"])
            result = current.get("result") or {}
            partial = clean_agent_response(result.get("partial_response")) if result.get("partial_response") else ""
            if partial and partial != last_sent:
                stream_message_id = self.send_stream_update(chat_id, stream_message_id, partial)
                last_sent = partial
            state = current.get("state")
            if state in TERMINAL_TASK_STATES:
                if state in {"failed", "dead_letter"}:
                    reply = owner_safe_runtime_failure(text, snapshot)
                else:
                    reply = format_transition(SIGNIFICANT_STATES.get(state, state), current, mode="chat")
                if reply and reply != last_sent:
                    stream_message_id = self.send_stream_update(chat_id, stream_message_id, reply)
                    last_sent = reply
                if last_sent:
                    self.remember_orchestrator_message(last_sent)
                self.state.data.setdefault("tracked", {}).pop(task["task_id"], None)
                self.state.save()
                return
            if first_reply_at and not last_sent and now >= first_reply_at:
                reply = build_realtime_owner_reply(text, snapshot)
                stream_message_id = self.send_stream_update(chat_id, stream_message_id, reply)
                last_sent = reply
            time.sleep(1)
        if not last_sent:
            self.state.save()

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
        self.state.data["owner_chat_id"] = message["chat"]["id"]
        if text.startswith("/"):
            self.remember_owner_message(text, "command")
            self.handle_command(message, text)
        elif wants_image_generation(text):
            self.remember_owner_message(text, "image")
            self.submit_image_task(message, text)
        elif wants_factory_task(text):
            self.remember_owner_message(text, "task")
            self.submit_text_task(message, text)
        elif should_answer_immediately(text):
            self.remember_owner_message(text, "chat")
            snapshot = self.conversation_snapshot()
            reply = build_realtime_owner_reply(text, snapshot)
            self.telegram.send_message(message["chat"]["id"], reply)
            self.remember_orchestrator_message(reply)
        else:
            self.remember_owner_message(text, "chat")
            self.submit_chat_task(message, text)

    def auto_track_owner_tasks(self) -> None:
        chat_id = self.owner_chat_id()
        if not chat_id:
            return
        try:
            tasks = self.factory.get_tasks().get("tasks", [])
        except Exception:
            return
        tracked = self.state.data.setdefault("tracked", {})
        since = self.state.data.get("common_chat_since")
        for task in tasks:
            task_id = task.get("task_id")
            if not task_id or task_id in tracked:
                continue
            if not owner_visible_task(task, since):
                continue
            tracked[task_id] = {"chat_id": chat_id, "last_state": "WATCHING", "mode": "task"}
        self.state.save()

    def poll_task_transitions(self) -> None:
        self.auto_track_owner_tasks()
        tracked = dict(self.state.data.get("tracked", {}))
        for task_id, record in tracked.items():
            task = self.factory.get_task(task_id)
            state = task.get("state")
            label = SIGNIFICANT_STATES.get(state)
            if label and label != record.get("last_state"):
                mode = record.get("mode", "task")
                if mode == "chat" and label not in {"COMPLETED", "FAILED"}:
                    self.state.data["tracked"][task_id]["last_state"] = label
                    self.state.save()
                    continue
                if mode == "image" and label not in {"COMPLETED", "FAILED"}:
                    self.state.data["tracked"][task_id]["last_state"] = label
                    self.state.save()
                    continue
                if mode == "image" and label == "COMPLETED":
                    try:
                        reply = self.send_image_result(int(record["chat_id"]), task)
                    except Exception:
                        reply = "Картинка сгенерирована, но Telegram не смог её принять. Я зафиксировал сбой доставки."
                        self.telegram.send_message(int(record["chat_id"]), reply)
                    record_task_transition(self.memory(), task, label, utc_now())
                    record_orchestrator_message(self.memory(), reply, utc_now())
                    self.state.data["tracked"].pop(task_id, None)
                    self.state.save()
                    continue
                if mode == "image" and label == "FAILED":
                    reply = "Сейчас не смог сгенерировать изображение. Я зафиксировал сбой и продолжу восстановление."
                    self.telegram.send_message(int(record["chat_id"]), reply)
                    record_task_transition(self.memory(), task, label, utc_now())
                    record_orchestrator_message(self.memory(), reply, utc_now())
                    self.state.data["tracked"].pop(task_id, None)
                    self.state.save()
                    continue
                reply = format_transition(label, task, mode)
                self.telegram.send_message(int(record["chat_id"]), reply)
                record_task_transition(self.memory(), task, label, utc_now())
                record_orchestrator_message(self.memory(), reply, utc_now())
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


def owner_visible_task(task: dict[str, Any], since: str | None = None) -> bool:
    task_id = str(task.get("task_id") or "")
    if task_id.startswith("TGCHAT-"):
        return False
    if since and iso_timestamp(task.get("created_at")) < iso_timestamp(since):
        return False
    envelope = task.get("envelope") or {}
    source = envelope.get("source") or {}
    if envelope.get("kind") == "owner_remote_task":
        return True
    return str(source.get("kind") or "").startswith("telegram")


def format_task_status(task: dict[str, Any]) -> str:
    result = task.get("result") or {}
    envelope = task.get("envelope") or {}
    partial = clean_agent_response(result.get("partial_response")) if result.get("partial_response") else ""
    if partial and task.get("state") in {"leased", "running", "review"}:
        return partial
    if envelope.get("kind") == "owner_remote_task" and task.get("state") in {"queued", "leased", "running"}:
        return "Задача в работе. Я держу её в поле зрения и пришлю сюда только понятное обновление или результат."
    if task.get("state") == "completed" and envelope.get("kind") == "owner_remote_task":
        response = clean_agent_response(result.get("response"))
        urls = extract_urls(response)
        lines = ["Готово. Удалённый исполнитель завершил задачу, я проверяю результат."]
        if urls:
            lines = [f"Готово. Проект запущен: {urls[0]}"]
            if len(urls) > 1:
                lines.append(f"API и документация: {urls[1]}")
        if "health" in response.lower() or "healthy" in response.lower():
            lines.append("Проверки живые: веб отвечает, backend отвечает, база работает.")
        return "\n".join(lines)
    lines = [human_task_state(task.get("state"))]
    pr_url = result.get("pull_request_url") or result.get("pr_url")
    if pr_url:
        lines.append(f"PR готов: {pr_url}")
    return "\n".join(lines)


def clean_agent_response(text: str | None) -> str:
    raw_lowered = (text or "").lower()
    if any(marker in raw_lowered for marker in OWNER_RUNTIME_FAILURE_MARKERS):
        return owner_safe_runtime_failure("", None)
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
    for wrong, right in OWNER_RESPONSE_REPLACEMENTS.items():
        cleaned = cleaned.replace(wrong, right)
    return cleaned or "Я завершил ответ, но текст не записался. Разберу это отдельно."


def extract_urls(text: str) -> list[str]:
    urls = []
    for match in re.findall(r"https?://[^\s`),]+", text):
        if match not in urls:
            urls.append(match)
    return urls


def _first_value(data: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = data.get(key)
        if value:
            return value
    return None


def clean_image_caption(text: str | None) -> str:
    caption = clean_agent_response(text)
    if caption == "Я завершил ответ, но текст не записался. Разберу это отдельно.":
        return "Готово."
    return caption[:1024]


def decode_image_b64(value: str) -> tuple[bytes, str | None]:
    mime_type = None
    payload = value.strip()
    if payload.startswith("data:") and ";base64," in payload:
        header, payload = payload.split(";base64,", 1)
        mime_type = header.removeprefix("data:") or None
    return base64.b64decode(payload), mime_type


def image_delivery_from_task(task: dict[str, Any]) -> dict[str, Any]:
    result = task.get("result") or {}
    image_data = result
    images = result.get("images")
    if isinstance(images, list) and images:
        first = images[0]
        if isinstance(first, dict):
            image_data = {**result, **first}
        elif isinstance(first, str):
            image_data = {**result, "image_url": first}
    mime_type = _first_value(image_data, ("image_mime_type", "mime_type", "content_type"))
    caption = _first_value(image_data, ("caption", "message", "response"))
    b64_value = _first_value(image_data, ("image_b64", "image_base64", "photo_b64", "b64_json"))
    if isinstance(b64_value, str):
        photo, detected_mime = decode_image_b64(b64_value)
        return {"photo": photo, "mime_type": mime_type or detected_mime or "image/png", "caption": caption}
    photo_url = _first_value(image_data, ("image_url", "photo_url", "url"))
    if isinstance(photo_url, str) and photo_url.startswith(("http://", "https://")):
        return {"photo": photo_url, "mime_type": mime_type, "caption": caption}
    image_path = _first_value(image_data, ("image_path", "photo_path", "artifact_path"))
    if isinstance(image_path, str):
        return {"photo": image_path, "mime_type": mime_type, "caption": caption}
    return {"photo": None, "mime_type": mime_type, "caption": caption}


def format_transition(label: str, task: dict[str, Any], mode: str = "task") -> str:
    result = task.get("result") or {}
    if mode == "chat" and label == "COMPLETED":
        return clean_agent_response(result.get("response") or result.get("partial_response"))
    if mode == "image" and label == "COMPLETED":
        delivery = image_delivery_from_task(task)
        if delivery.get("photo"):
            return clean_image_caption(delivery.get("caption")) or "Готово, отправил изображение."
        return "Картинка сгенерирована, но я не получил файл для отправки в Telegram."
    if mode == "chat" and label == "FAILED":
        return "Сейчас не смог подготовить ответ. Я зафиксировал сбой и продолжу восстановление."
    if mode == "image" and label == "FAILED":
        return "Сейчас не смог сгенерировать изображение. Я зафиксировал сбой и продолжу восстановление."
    return format_task_status(task)


def handle_stop(signum: int, frame: Any) -> None:
    del signum, frame
    global STOP
    STOP = True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--control-url", default=os.environ.get("KOLIBRI_FACTORY_CONTROL_URL", "http://10.99.0.2:9101"))
    parser.add_argument("--control-urls", default=os.environ.get("KOLIBRI_FACTORY_CONTROL_URLS") or os.environ.get("KOLIBRI_FACTORY_CONTROL_URL", "http://10.99.0.2:9101"))
    parser.add_argument("--state-file", default=os.environ.get("TELEGRAM_GATEWAY_STATE", "/var/lib/kolibri-telegram-gateway/state.json"))
    parser.add_argument("--poll-timeout", type=int, default=int(os.environ.get("TELEGRAM_POLL_TIMEOUT", "25")))
    args = parser.parse_args()
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    owner_ids = parse_owner_ids(os.environ.get("TELEGRAM_OWNER_IDS", ""))
    if not owner_ids:
        raise SystemExit("TELEGRAM_OWNER_IDS is required")
    signal.signal(signal.SIGTERM, handle_stop)
    signal.signal(signal.SIGINT, handle_stop)
    gateway = Gateway(TelegramClient(token), FactoryClient(args.control_url, args.control_urls), owner_ids, StateStore(Path(args.state_file)), args.poll_timeout)
    gateway.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
