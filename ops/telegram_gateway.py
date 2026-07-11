#!/usr/bin/env python3
"""Telegram long-polling gateway for the Kolibri Factory control plane."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import mimetypes
import os
import re
import signal
import stat
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from ops.control_plane_endpoint import resolve_home_control_plane_url
except ImportError:  # installed standalone beside this script
    from control_plane_endpoint import resolve_home_control_plane_url

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))
from orchestrator_roster import ORCHESTRATOR_CARD, node_card
from telegram_superfactory import plan_update_receiver, redacted_receiver_status
from orchestrator_memory import (
    empty_memory,
    ensure_memory,
    memory_snapshot,
    record_orchestrator_message,
    record_owner_message,
    record_task_transition,
    record_work_task,
)
from telegram_failover_guard import (
    GATEWAY_ROLE_PRIMARY,
    GATEWAY_ROLE_STANDBY,
    detect_dual_receiver,
    load_failover_state,
    validate_gateway_startup,
)


STOP = False
DELIVERY_STATE_MUTATION_METHODS = frozenset({"deleteWebhook", "setWebhook", "logOut", "close"})
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
TOKEN_LIKE_RE = re.compile(
    r"(?i)(?:\b\d{6,}:[A-Za-z0-9_-]{20,}\b|\b(?:ghp|github_pat|xox[baprs]|sk)-[A-Za-z0-9_-]{16,}\b|\b[A-Fa-f0-9]{40,}\b)"
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
DEFAULT_BACKEND_URL = "http://127.0.0.1:8001"
DEFAULT_OWNER_TOKEN_FILE = "/etc/kolibri/owner-api-token"
PROCESSED_UPDATE_LIMIT = 4096
PROCESSED_MESSAGE_LIMIT = 4096
WEB_FRESHNESS_MARKERS = (
    "сегодня",
    "сейчас",
    "актуаль",
    "последн",
    "новост",
    "погод",
    "пробк",
    "расписан",
    "курс ",
    "цена",
    "стоимост",
    "в наличии",
    "где купить",
    "рекоменд",
    "посовет",
    "что лучше",
    "какие лучше",
    "лучше поставить",
    "лучше выбрать",
    "какие выбрать",
    "какой выбрать",
    "какую выбрать",
    "что выбрать",
    "какие поставить",
    "best ",
    "recommend",
    "latest",
    "current ",
    "today",
    "weather",
    "news",
    "price",
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


class ResponsesClientError(RuntimeError):
    """Normalized owner-safe failure from the unified Responses API."""

    def __init__(self, code: str, *, http_status: int | None = None):
        super().__init__(code)
        self.code = _safe_error_code(code)
        self.http_status = http_status


def _safe_error_code(value: Any, fallback: str = "responses_unavailable") -> str:
    code = re.sub(r"[^a-z0-9_.:-]+", "_", str(value or "").strip().lower()).strip("_.:-")
    return (code or fallback)[:96]


def load_owner_bearer_token(path: str | Path) -> str:
    """Read the owner bearer from a protected file without logging its value.

    Production uses a root-owned, group-readable ``0640`` file for the
    ``kolibri`` service.  A user-owned ``0600`` file is also accepted for local
    development and tests.  Symlinks, group-writable files and every
    world-accessible mode fail closed.
    """

    candidate = Path(path).expanduser()
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(candidate, flags)
    except OSError as exc:
        raise ResponsesClientError("owner_bearer_file_unreadable") from exc
    try:
        info = os.fstat(descriptor)
        mode = stat.S_IMODE(info.st_mode)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid not in {0, os.getuid()}
            or mode & 0o027
            or not mode & 0o400
            or not 8 <= info.st_size <= 4096
        ):
            raise ResponsesClientError("owner_bearer_file_unsafe")
        try:
            with os.fdopen(descriptor, "r", encoding="utf-8") as handle:
                descriptor = -1
                raw = handle.read(4097)
        except (OSError, UnicodeError) as exc:
            raise ResponsesClientError("owner_bearer_file_unreadable") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    token = raw.strip()
    if not token or len(token) > 2048 or any(ch.isspace() for ch in token):
        raise ResponsesClientError("owner_bearer_file_invalid")
    return token


def normalize_backend_url(value: str | None) -> str:
    raw = str(value or DEFAULT_BACKEND_URL).strip().rstrip("/")
    parsed = urllib.parse.urlsplit(raw)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("invalid Kolibri backend URL")
    return raw


def response_output_text(payload: dict[str, Any]) -> str:
    direct = payload.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    parts: list[str] = []
    for item in payload.get("output") or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content") or []:
            if not isinstance(content, dict):
                continue
            if content.get("type") not in {"output_text", "text"}:
                continue
            text = content.get("text")
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
    return "\n".join(parts).strip()


def response_error_code(payload: dict[str, Any]) -> str:
    error = payload.get("error")
    if isinstance(error, dict):
        return _safe_error_code(error.get("code") or error.get("type"))
    if isinstance(error, str):
        return _safe_error_code(error)
    incomplete = payload.get("incomplete_details")
    if isinstance(incomplete, dict):
        return _safe_error_code(incomplete.get("reason"), "response_incomplete")
    status = _safe_error_code(payload.get("status"), "response_without_output")
    return "response_without_output" if status == "completed" else status


def needs_web_search(text: str) -> bool:
    lowered = " ".join(text.casefold().split())
    return any(marker in lowered for marker in WEB_FRESHNESS_MARKERS)


class ResponsesClient:
    """Thin OpenAI-compatible client for Home's unified backend."""

    def __init__(
        self,
        backend_url: str = DEFAULT_BACKEND_URL,
        owner_token_file: str | Path = DEFAULT_OWNER_TOKEN_FILE,
        *,
        timeout: int = 120,
        poll_interval: float = 0.5,
    ):
        self.backend_url = normalize_backend_url(backend_url)
        self.owner_token_file = Path(owner_token_file).expanduser()
        self.timeout = max(1, int(timeout))
        self.poll_interval = max(0.05, float(poll_interval))

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        token = load_owner_bearer_token(self.owner_token_file)
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        data = None if body is None else json.dumps(
            body, ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.backend_url}{path}", data=data, method=method, headers=headers,
        )

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *_args: Any, **_kwargs: Any) -> None:
                return None

        try:
            with urllib.request.build_opener(NoRedirect()).open(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                payload = json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            try:
                raw_error = json.loads(exc.read().decode("utf-8", "replace"))
            except (json.JSONDecodeError, UnicodeError):
                raw_error = {}
            detail = raw_error.get("detail") if isinstance(raw_error, dict) else None
            if isinstance(detail, dict):
                detail = detail.get("code") or detail.get("type")
            error = raw_error.get("error") if isinstance(raw_error, dict) else None
            if isinstance(error, dict):
                error = error.get("code") or error.get("type")
            raise ResponsesClientError(
                _safe_error_code(error or detail, f"responses_http_{exc.code}"),
                http_status=exc.code,
            ) from exc
        except (OSError, TimeoutError, urllib.error.URLError) as exc:
            raise ResponsesClientError("responses_backend_unavailable") from exc
        except (json.JSONDecodeError, UnicodeError) as exc:
            raise ResponsesClientError("responses_invalid_json") from exc
        if not isinstance(payload, dict):
            raise ResponsesClientError("responses_invalid_payload")
        return payload

    def create_response(
        self,
        *,
        text: str,
        chat_id: int,
        message_id: int,
        previous_response_id: str | None = None,
        web_search: bool = False,
    ) -> dict[str, Any]:
        idempotency_key = f"telegram-response:{chat_id}:{message_id}"
        body: dict[str, Any] = {
            "model": "kolibri",
            "input": text,
            "stream": False,
            "idempotency_key": idempotency_key,
            "metadata": {
                "source": "telegram",
                "chat_id_sha256": hashlib.sha256(str(chat_id).encode("utf-8")).hexdigest(),
                "message_id": message_id,
            },
        }
        if previous_response_id:
            body["previous_response_id"] = previous_response_id
        if web_search:
            body["tools"] = [{"type": "web_search", "search_context_size": "medium"}]
        payload = self._request(
            "POST", "/v1/responses", body=body, idempotency_key=idempotency_key,
        )
        deadline = time.monotonic() + self.timeout
        while str(payload.get("status") or "").lower() in {
            "queued", "planning", "running", "verifying", "in_progress",
        }:
            response_id = payload.get("id")
            if not response_id or time.monotonic() >= deadline:
                raise ResponsesClientError("response_timeout")
            time.sleep(self.poll_interval)
            payload = self._request(
                "GET", f"/v1/responses/{urllib.parse.quote(str(response_id), safe='')}",
            )
        output_text = response_output_text(payload)
        if str(payload.get("status") or "").lower() != "completed" or not output_text:
            raise ResponsesClientError(response_error_code(payload))
        payload["output_text"] = output_text
        return payload


class TelegramClient:
    def __init__(
        self,
        token: str,
        api_base: str = "https://api.telegram.org",
        allow_delivery_state_mutation: bool = False,
    ):
        if not token:
            raise ValueError("Telegram token is required")
        self.api_base = api_base.rstrip("/")
        self.base_url = f"{self.api_base}/bot{token}"
        self.allow_delivery_state_mutation = allow_delivery_state_mutation

    def call(self, method: str, payload: dict[str, Any] | None = None, timeout: int = 35) -> dict[str, Any]:
        if method in DELIVERY_STATE_MUTATION_METHODS and not self.allow_delivery_state_mutation:
            raise RuntimeError(f"telegram delivery-state mutation is not allowed from gateway startup: {method}")
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
        self.control_url = resolve_home_control_plane_url(control_url, control_urls)

    def request(self, method: str, path: str, body: dict[str, Any] | None = None, timeout: int = 35) -> Any:
        return json_request(method, f"{self.control_url}{path}", body, timeout=timeout)

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
        return self.request("GET", "/v1/nodes?scope=active&limit=250")


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
                "runners": node.get("runners", {}),
                "draining": bool(node.get("draining")),
                "schedulable": bool(node.get("schedulable", True)),
                "heartbeat_at": node.get("heartbeat_at"),
                "freshness": node.get("freshness"),
                "heartbeat_age_seconds": node.get("heartbeat_age_seconds"),
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


def runner_capability_names(runner: str) -> set[str]:
    return {f"runner:{runner}", f"runner_{runner}", f"{runner}_runner"}


def node_available_for_execution(node: dict[str, Any]) -> bool:
    if node.get("health") != "online" or node.get("draining"):
        return False
    return True


def runner_node_available(node: dict[str, Any], runner: str) -> bool:
    if not node_available_for_execution(node):
        return False
    capabilities = set(node.get("capabilities") or [])
    if not runner_capability_names(runner).intersection(capabilities):
        return False
    runners = node.get("runners") if isinstance(node.get("runners"), dict) else {}
    state = runners.get(runner)
    if isinstance(state, dict):
        state = state.get("status")
    if str(state or "available").strip().lower() in {"blocked", "degraded", "runner_auth_blocked", "unavailable"}:
        return False
    return True


def select_execution_node(
    snapshot: dict[str, Any],
    *,
    required_capability: str | None = None,
    runner: str | None = None,
    avoided: list[str] | None = None,
) -> str | None:
    """Select only a live member advertising the requested runtime contract.

    The Home Control Plane remains authoritative when no local snapshot is
    available: callers omit ``target_node`` and let the same capability and
    runner constraints drive lease scheduling.  A historical hostname is
    never synthesized as a fallback.
    """

    avoided_set = set(avoided or [])
    for node in snapshot.get("nodes") or []:
        node_id = node.get("node_id")
        if not node_id or node_id in avoided_set or not node_available_for_execution(node):
            continue
        capabilities = set(node.get("capabilities") or [])
        if required_capability and required_capability not in capabilities:
            continue
        if runner and not runner_node_available(node, runner):
            continue
        return str(node_id)
    return None


def select_runner_node(snapshot: dict[str, Any], runner: str, avoided: list[str] | None = None) -> str | None:
    return select_execution_node(snapshot, runner=runner, avoided=avoided)


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
    target_node = os.environ.get("TELEGRAM_TASK_NODE")
    if target_node:
        envelope["target_node"] = target_node
    return envelope


def build_chat_envelope(message: dict[str, Any], text: str, snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    task_id = chat_task_id_from_message(message)
    context = snapshot or {}
    runner = os.environ.get("TELEGRAM_CHAT_RUNNER", "codex")
    objective = (
        "Сгенерируй живой короткий ответ владельцу проекта в Telegram. "
        "Отвечай как директор-оркестратор проекта: естественно, по-русски, без заготовок, без markdown, "
        "без task_id, node, agent, путей, команд и служебных деталей. "
        "Не называй себя брендом продукта. Если владелец просто здоровается, ответь по-человечески и мягко, "
        "но не используй заранее заданную фразу. Если владелец спрашивает о работе, используй контекст фабрики. "
        f"Контекст фабрики: {json.dumps(context, ensure_ascii=False, sort_keys=True)}\n"
        f"Сообщение владельца: {text}"
    )
    required_capability = os.environ.get("TELEGRAM_CHAT_CAPABILITY", "generic_implementation")
    envelope = {
        "task_id": task_id,
        "idempotency_key": f"telegram-chat:{message['chat']['id']}:{message['message_id']}",
        "kind": os.environ.get("TELEGRAM_CHAT_KIND", "owner_remote_task"),
        "required_capability": required_capability,
        "max_retries": 1,
        "message": text,
        "objective": objective,
        "runner": runner,
        "factory_snapshot": context,
        "source": {
            "kind": "telegram",
            "message_id": message["message_id"],
            "chat_id": message["chat"]["id"],
            "user_id": message["from"]["id"],
            "accepted_at": utc_now(),
        },
    }
    target_node = os.environ.get("TELEGRAM_CHAT_NODE")
    if not target_node and context.get("nodes"):
        target_node = select_execution_node(
            context,
            required_capability=required_capability,
            runner=runner,
            avoided=envelope.get("avoid_nodes"),
        )
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
    required_capability = os.environ.get("TELEGRAM_IMAGE_CAPABILITY", "image_generation")
    runner = str(os.environ.get("TELEGRAM_IMAGE_RUNNER") or "").strip().lower()
    envelope = {
        "task_id": task_id,
        "idempotency_key": f"telegram-image:{message['chat']['id']}:{message['message_id']}",
        "kind": os.environ.get("TELEGRAM_IMAGE_KIND", "telegram_image_generation"),
        "required_capability": required_capability,
        "max_retries": int(os.environ.get("TELEGRAM_IMAGE_MAX_RETRIES", "1")),
        "message": text,
        "prompt": text,
        "objective": prompt,
        "factory_snapshot": context,
        "source": {
            "kind": "telegram",
            "message_id": message["message_id"],
            "chat_id": message["chat"]["id"],
            "user_id": message["from"]["id"],
            "accepted_at": utc_now(),
        },
    }
    if runner:
        envelope["runner"] = runner
    target_node = os.environ.get("TELEGRAM_IMAGE_NODE")
    if not target_node and context.get("nodes"):
        target_node = select_execution_node(
            context,
            required_capability=required_capability,
            runner=runner or None,
            avoided=envelope.get("avoid_nodes"),
        )
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
        "Пишите обычным языком или используйте /ask <вопрос>. Диалог идёт через Kolibri Factory "
        "с продолжением контекста. /status показывает живое состояние узлов и очереди; "
        "остальные режимы фабрика выбирает сама."
    )


def start_text() -> str:
    return (
        "Kolibri готов к диалогу. Задавайте вопрос, просите подобрать решение, составить документ "
        "или спланировать работу — ответ выполнит реальная фабрика. Команды и режимы: /help."
    )


def format_factory_snapshot(snapshot: dict[str, Any]) -> str:
    nodes = snapshot.get("nodes") or []
    total = len(nodes)
    online = sum(1 for node in nodes if node.get("health") == "online")
    schedulable = sum(
        1 for node in nodes
        if node.get("health") == "online"
        and node.get("freshness") != "stale"
        and not node.get("draining")
        and node.get("schedulable", True)
    )
    active = len(snapshot.get("active_tasks") or [])
    queue_length = int(snapshot.get("queue_length") or 0)
    counts = snapshot.get("task_counts") or {}
    completed = int(counts.get("completed") or 0)
    failed = sum(int(counts.get(state) or 0) for state in ("failed", "dead_letter"))
    lines = [
        "Kolibri Factory — живой статус",
        f"Узлы: online {online}/{total}; готовы к работе {schedulable}/{total}",
        f"Задачи: активные {active}; очередь {queue_length}; завершено {completed}; ошибки {failed}",
    ]
    warnings = snapshot.get("warnings") or []
    if warnings:
        unavailable = []
        if any(str(item).startswith("nodes_unavailable:") for item in warnings):
            unavailable.append("узлы")
        if any(str(item).startswith("tasks_unavailable:") for item in warnings):
            unavailable.append("задачи")
        lines.append("Недоступны данные: " + ", ".join(unavailable or ["часть телеметрии"]))
    lines.append(f"Снимок: {snapshot.get('captured_at') or utc_now()}")
    return "\n".join(lines)


class StateStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self.load()

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            data = {
                "offset": None,
                "tracked": {},
                "memory": empty_memory(),
                "processed_updates": {},
                "processed_messages": {},
                "previous_response_ids": {},
            }
        else:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        data.setdefault("offset", None)
        data.setdefault("tracked", {})
        data.setdefault("processed_updates", {})
        data.setdefault("processed_messages", {})
        data.setdefault("previous_response_ids", {})
        data.setdefault("common_chat_since", os.environ.get("TELEGRAM_COMMON_CHAT_SINCE", utc_now()))
        ensure_memory(data)
        return data

    def save(self) -> None:
        payload = json.dumps(self.data, indent=2, sort_keys=True) + "\n"
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent,
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary_name, 0o600)
            os.replace(temporary_name, self.path)
            directory_fd = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass

    @staticmethod
    def _trim_records(records: dict[str, Any], limit: int) -> None:
        overflow = len(records) - limit
        if overflow > 0:
            for key in list(records)[:overflow]:
                records.pop(key, None)

    @staticmethod
    def message_key(message: dict[str, Any] | None) -> str | None:
        if not message:
            return None
        chat_id = (message.get("chat") or {}).get("id")
        message_id = message.get("message_id")
        if chat_id is None or message_id is None:
            return None
        return f"{chat_id}:{message_id}"

    def claim_message(self, message: dict[str, Any]) -> bool:
        """Persist message dedupe before any Telegram or factory side effect."""

        key = self.message_key(message)
        if key is None:
            return False
        processed = self.data.setdefault("processed_messages", {})
        if key in processed:
            return False
        processed[key] = utc_now()
        self._trim_records(processed, PROCESSED_MESSAGE_LIMIT)
        self.save()
        return True

    def claim_update(self, update: dict[str, Any]) -> bool:
        """Atomically advance the inbox and claim an update at most once."""

        update_id = update.get("update_id")
        if update_id is None:
            return False
        key = str(update_id)
        updates = self.data.setdefault("processed_updates", {})
        message_key = self.message_key(update.get("message"))
        messages = self.data.setdefault("processed_messages", {})
        already_processed = key in updates or bool(message_key and message_key in messages)
        self.data["offset"] = max(int(self.data.get("offset") or 0), int(update_id) + 1)
        if not already_processed:
            updates[key] = utc_now()
            if message_key:
                messages[message_key] = utc_now()
            self._trim_records(updates, PROCESSED_UPDATE_LIMIT)
            self._trim_records(messages, PROCESSED_MESSAGE_LIMIT)
        self.save()
        return not already_processed


class Gateway:
    def __init__(self, telegram: TelegramClient, factory: FactoryClient, owner_ids: set[int], state: StateStore, poll_timeout: int, gateway_role: str = GATEWAY_ROLE_PRIMARY):
        self.telegram = telegram
        self.factory = factory
        self.responses: ResponsesClient | None = getattr(factory, "responses_client", None)
        self.owner_ids = owner_ids
        self.state = state
        self.poll_timeout = poll_timeout
        self.gateway_role = gateway_role

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

    def submit_response(self, message: dict[str, Any], text: str) -> None:
        """Answer one Telegram input through Home's OpenAI-compatible API."""

        chat_id = int(message["chat"]["id"])
        message_id = int(message["message_id"])
        previous = self.state.data.setdefault("previous_response_ids", {}).get(str(chat_id))
        try:
            try:
                self.telegram.send_action(chat_id)
            except Exception:
                # Typing state is cosmetic; it must never replace the answer.
                pass
            if self.responses is None:
                raise ResponsesClientError("responses_client_not_configured")
            payload = self.responses.create_response(
                text=text,
                chat_id=chat_id,
                message_id=message_id,
                previous_response_id=str(previous) if previous else None,
                web_search=needs_web_search(text),
            )
            reply = TOKEN_LIKE_RE.sub("[скрыто]", str(payload["output_text"]).strip())
            response_id = payload.get("id")
            if response_id:
                self.state.data.setdefault("previous_response_ids", {})[str(chat_id)] = str(response_id)
            self.remember_orchestrator_message(reply)
        except ResponsesClientError as exc:
            reply = f"Kolibri Factory не смогла вернуть ответ ({exc.code}). Попробуйте повторить запрос позже."
            self.remember_orchestrator_message(reply)
        except Exception:
            reply = "Kolibri Factory не смогла вернуть ответ (responses_internal_error). Попробуйте повторить запрос позже."
            self.remember_orchestrator_message(reply)
        self.telegram.send_message(chat_id, reply)

    def handle_command(self, message: dict[str, Any], text: str) -> None:
        chat_id = message["chat"]["id"]
        command, _, arg = text.partition(" ")
        command = command.split("@", 1)[0]
        arg = arg.strip()
        if command == "/start":
            self.telegram.send_message(chat_id, start_text())
        elif command == "/help":
            self.telegram.send_message(chat_id, help_text())
        elif command == "/ask" and arg:
            self.submit_response(message, arg)
        elif command == "/ask":
            self.telegram.send_message(chat_id, "После /ask напишите вопрос, например: /ask какие динамики выбрать для Hyundai Solaris?")
        elif command == "/task" and arg:
            self.submit_text_task(message, arg)
        elif command == "/status":
            if arg:
                try:
                    task = self.factory.get_task(arg)
                    reply = format_task_status(task)
                except Exception:
                    reply = "Не удалось получить статус этой задачи из Home Control Plane."
            else:
                reply = format_factory_snapshot(self.conversation_snapshot())
            self.telegram.send_message(chat_id, reply)
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

    def handle_message(self, message: dict[str, Any], *, preclaimed: bool = False) -> None:
        if not preclaimed and not self.state.claim_message(message):
            return
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
        else:
            self.remember_owner_message(text, "chat")
            self.submit_response(message, text)

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
        if os.environ.get("TELEGRAM_AUTO_TRACK_OWNER_TASKS", "0") == "1":
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
                    # Persist terminal delivery before Telegram side effects so
                    # a restart cannot send the same result twice.
                    self.state.data["tracked"].pop(task_id, None)
                    record_task_transition(self.memory(), task, label, utc_now())
                    self.state.save()
                    try:
                        reply = self.send_image_result(int(record["chat_id"]), task)
                    except Exception:
                        reply = "Картинка сгенерирована, но Telegram не смог её принять. Я зафиксировал сбой доставки."
                        self.telegram.send_message(int(record["chat_id"]), reply)
                    record_orchestrator_message(self.memory(), reply, utc_now())
                    self.state.save()
                    continue
                if mode == "image" and label == "FAILED":
                    reply = "Сейчас не смог сгенерировать изображение. Я зафиксировал сбой и продолжу восстановление."
                    self.state.data["tracked"].pop(task_id, None)
                    record_task_transition(self.memory(), task, label, utc_now())
                    self.state.save()
                    self.telegram.send_message(int(record["chat_id"]), reply)
                    record_orchestrator_message(self.memory(), reply, utc_now())
                    self.state.save()
                    continue
                reply = format_transition(label, task, mode)
                if label in {"COMPLETED", "FAILED", "CANCELLED"}:
                    self.state.data["tracked"].pop(task_id, None)
                else:
                    self.state.data["tracked"][task_id]["last_state"] = label
                record_task_transition(self.memory(), task, label, utc_now())
                self.state.save()
                self.telegram.send_message(int(record["chat_id"]), reply)
                record_orchestrator_message(self.memory(), reply, utc_now())
                self.state.save()

    def run_once(self) -> None:
        failover_state = load_failover_state(self.state.path.parent / "failover.json")
        detection = detect_dual_receiver(
            primary_polling=self.gateway_role == GATEWAY_ROLE_PRIMARY,
            standby_polling=self.gateway_role == GATEWAY_ROLE_STANDBY,
            webhook_active=False,
        )
        if not detection["ok"]:
            print(json.dumps({"event": "ha_dual_receiver_violation", "violations": detection["violations"]}, sort_keys=True), file=sys.stderr)
            return
        if self.gateway_role == GATEWAY_ROLE_STANDBY and failover_state.primary_healthy:
            return
        updates = self.telegram.get_updates(self.state.data.get("offset"), self.poll_timeout)
        for update in updates:
            if not self.state.claim_update(update):
                continue
            message = update.get("message")
            if message:
                self.handle_message(message, preclaimed=True)
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
    freshness = card.get("freshness") or card["health"]
    age = card.get("heartbeat_age_seconds")
    age_text = "unknown" if age is None else f"{age}s"
    return f"{card['name']} — {card['role']}\nСостояние: {card['health']} ({freshness}, heartbeat {age_text})\nЗадача: {card['responsibility']}"


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
        gomesh_card = format_gomesh_status_report(result.get("response"))
        if gomesh_card:
            return gomesh_card
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


def _safe_report_text(text: str | None) -> str:
    if not text:
        return ""
    without_tokens = TOKEN_LIKE_RE.sub("[скрыто]", text)
    return without_tokens.replace("\r\n", "\n").replace("\r", "\n")


def _field_value(text: str, labels: tuple[str, ...]) -> str | None:
    for label in labels:
        pattern = rf"(?im)^\s*(?:[-*]\s*)?{label}\s*[:=]\s*(.+?)\s*$"
        match = re.search(pattern, text)
        if match:
            value = " ".join(match.group(1).strip(" `").split())
            if value and not TOKEN_LIKE_RE.search(value):
                return value
    return None


def _first_number(text: str, patterns: tuple[str, ...]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            return match.group(1).replace(",", ".")
    return None


def _pytest_pass_count(text: str) -> str | None:
    match = re.search(r"(?i)\b(\d+)\s+passed\b", text)
    if match:
        return match.group(1)
    return _field_value(text, ("pytest pass count", "pytest passed", "tests passed", "pass count"))


def _rollback_paths(text: str) -> list[str]:
    paths: list[str] = []
    for line in text.splitlines():
        lowered = line.lower()
        if not any(word in lowered for word in ("rollback", "backup", "backup path", "backup paths", "бэкап", "резерв")):
            continue
        for path in re.findall(r"(?:/[\w.@:+-]+)+(?:\.[\w.+-]+)?", line):
            if any(secret_word in path.lower() for secret_word in ("secret", "token", "passwd", "password", "psk", ".env")):
                continue
            if path not in paths:
                paths.append(path)
    return paths[:4]


def _failed_speed_gate(text: str, direct_mbps: str | None, gomesh_mbps: str | None, target_mbps: str | None) -> bool:
    lowered = text.lower()
    if re.search(r"(?i)(speed[-_ ]?gate|скоростн\w+ gate|гейт).{0,80}(fail|failed|не пройден|провален)", text):
        return True
    if re.search(r"(?i)(fail|failed|не пройден|провален).{0,80}(speed[-_ ]?gate|скоростн\w+ gate|гейт)", text):
        return True
    if "failed speed gate" in lowered or "speed gate failed" in lowered:
        return True
    if gomesh_mbps and target_mbps:
        try:
            return float(gomesh_mbps) < float(target_mbps)
        except ValueError:
            return False
    return False


def format_gomesh_status_report(text: str | None) -> str | None:
    """Turn noisy GoMesh speed/status reports into an owner-facing Telegram card."""
    report = _safe_report_text(text)
    lowered = report.lower()
    if not report or not ("gomesh" in lowered or "go mesh" in lowered):
        return None
    if not any(marker in lowered for marker in ("speed", "mbps", "selector", "rollback", "endpoint", "health")):
        return None

    home_endpoint = _field_value(report, ("home endpoint", "home", "endpoint", "домашний endpoint", "home_endpoint"))
    health = _field_value(report, ("health", "home health", "status health", "здоровье"))
    selector = _field_value(report, ("selector status", "selector", "selector_state", "статус селектора"))
    next_action = _field_value(report, ("next action", "next", "следующее действие", "next_action"))
    direct_mbps = _first_number(
        report,
        (
            r"\bdirect(?:\s+download)?(?:\s+mbps)?\s*[:=]\s*([0-9]+(?:[.,][0-9]+)?)",
            r"\bbaseline(?:\s+mbps)?\s*[:=]\s*([0-9]+(?:[.,][0-9]+)?)",
            r"\bпрям\w+(?:\s+канал)?(?:\s+mbps)?\s*[:=]\s*([0-9]+(?:[.,][0-9]+)?)",
        ),
    )
    gomesh_mbps = _first_number(
        report,
        (
            r"\bgomesh(?:\s+download)?(?:\s+mbps)?\s*[:=]\s*([0-9]+(?:[.,][0-9]+)?)",
            r"\bgo mesh(?:\s+download)?(?:\s+mbps)?\s*[:=]\s*([0-9]+(?:[.,][0-9]+)?)",
            r"\bчерез\s+gomesh(?:\s+mbps)?\s*[:=]\s*([0-9]+(?:[.,][0-9]+)?)",
        ),
    )
    target_mbps = _first_number(
        report,
        (
            r"\btarget\s*[:=]\s*([0-9]+(?:[.,][0-9]+)?)\+?\s*mbps",
            r"\b([0-9]+(?:[.,][0-9]+)?)\+\s*mbps\s+target\b",
            r"\bцель\s*[:=]\s*([0-9]+(?:[.,][0-9]+)?)\+?\s*mbps",
        ),
    ) or ("300" if re.search(r"(?i)\b300\+\s*mbps\b", report) else None)
    pytest_passed = _pytest_pass_count(report)
    rollback_paths = _rollback_paths(report)
    failed_gate = _failed_speed_gate(report, direct_mbps, gomesh_mbps, target_mbps)

    if not any((home_endpoint, health, direct_mbps, gomesh_mbps, target_mbps, selector, pytest_passed, rollback_paths)):
        return None

    lines = ["Kolibri GoMesh: статус speed-gate"]
    lines.append(f"Статус: {'не пройден' if failed_gate else 'проверка пройдена'}")
    if home_endpoint:
        lines.append(f"Home endpoint: {home_endpoint}")
    if health:
        lines.append(f"Health: {health}")
    metric_parts = []
    if direct_mbps:
        metric_parts.append(f"direct {direct_mbps} Mbps")
    if gomesh_mbps:
        metric_parts.append(f"GoMesh {gomesh_mbps} Mbps")
    if target_mbps:
        metric_parts.append(f"цель {target_mbps}+ Mbps")
    if metric_parts:
        lines.append("Метрики: " + "; ".join(metric_parts))
    if failed_gate:
        lines.append("Вердикт: speed-gate провален, 300+ Mbps через GoMesh не подтверждены.")
    else:
        lines.append("Вердикт: speed-gate без блокера по скорости.")
    if selector:
        lines.append(f"Selector: {selector}")
    if pytest_passed:
        lines.append(f"Тесты: pytest {pytest_passed} passed")
    if rollback_paths:
        lines.append("Rollback: " + "; ".join(rollback_paths))
    if next_action:
        lines.append(f"Следующее действие: {next_action}")
    elif failed_gate:
        lines.append("Следующее действие: оставить селектор в безопасном режиме и разбирать деградацию GoMesh до повторного переключения.")
    return "\n".join(lines[:10])


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
    parser.add_argument("--control-url", default=os.environ.get("KOLIBRI_FACTORY_CONTROL_URL"))
    parser.add_argument("--control-urls", default=os.environ.get("KOLIBRI_FACTORY_CONTROL_URLS"))
    parser.add_argument(
        "--backend-url",
        default=os.environ.get("KOLIBRI_BACKEND_URL", DEFAULT_BACKEND_URL),
    )
    parser.add_argument(
        "--owner-token-file",
        default=os.environ.get("KOLIBRI_OWNER_API_TOKEN_FILE", DEFAULT_OWNER_TOKEN_FILE),
    )
    parser.add_argument(
        "--response-timeout",
        type=int,
        default=int(os.environ.get("TELEGRAM_RESPONSE_TIMEOUT_SECONDS", "120")),
    )
    parser.add_argument("--state-file", default=os.environ.get("TELEGRAM_GATEWAY_STATE", "/var/lib/kolibri-telegram-gateway/state.json"))
    parser.add_argument("--poll-timeout", type=int, default=int(os.environ.get("TELEGRAM_POLL_TIMEOUT", "25")))
    args = parser.parse_args()
    args.control_url = resolve_home_control_plane_url(args.control_url, args.control_urls)
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    owner_ids = parse_owner_ids(os.environ.get("TELEGRAM_OWNER_IDS", ""))
    if not owner_ids:
        raise SystemExit("TELEGRAM_OWNER_IDS is required")
    signal.signal(signal.SIGTERM, handle_stop)
    signal.signal(signal.SIGINT, handle_stop)
    telegram = TelegramClient(token)
    receiver_plan = plan_update_receiver()
    print(json.dumps({"event": "telegram_receiver_plan", **redacted_receiver_status(receiver_plan)}, sort_keys=True))
    if not receiver_plan.should_poll:
        raise SystemExit(f"canonical Telegram receiver refused to start polling: {receiver_plan.conflict or receiver_plan.startup_action}")
    state_path = Path(args.state_file)
    failover_state = load_failover_state(state_path.parent / "failover.json")
    gateway_role = os.environ.get("TELEGRAM_GATEWAY_ROLE", GATEWAY_ROLE_PRIMARY)
    primary_healthy = failover_state.primary_healthy
    startup_validation = validate_gateway_startup(
        role=gateway_role,
        update_receiver="polling",
        webhook_url=None,
        primary_healthy=primary_healthy,
    )
    print(json.dumps({"event": "telegram_ha_startup_validation", **startup_validation}, sort_keys=True))
    if not startup_validation["ok"]:
        violations = startup_validation["violations"]
        raise SystemExit(f"HA guard rejected gateway startup: {violations}")
    factory = FactoryClient(args.control_url)
    factory.responses_client = ResponsesClient(
        args.backend_url,
        args.owner_token_file,
        timeout=args.response_timeout,
    )
    gateway = Gateway(
        telegram,
        factory,
        owner_ids,
        StateStore(state_path),
        args.poll_timeout,
        gateway_role=gateway_role,
    )
    gateway.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
