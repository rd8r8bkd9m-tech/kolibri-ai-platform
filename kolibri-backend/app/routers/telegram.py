"""Telegram channel adapter for the canonical Kolibri response contract.

This module deliberately contains no polling loop, watchdog, GoMesh reporter
or direct Bot API sender.  A configured Telegram webhook can return exactly
one method payload for a new update; repeated updates are acknowledged without
another send action.  Conversation state uses the same durable project/message
repository as the Shell, and execution uses the same Codex-first response
service as ``POST /v1/responses``.
"""

from __future__ import annotations

import hmac
import json
import os
import re
from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.project_history import ProjectConflictError, ProjectHistoryRepository
from app.routers.openai_compat import ResponsesRequest, execute_kolibri_response


router = APIRouter(prefix="/api/v1/telegram", tags=["telegram"])

_TRUE = {"1", "true", "yes", "on"}
_BLOCKED_BACKGROUND_SENDERS = ("watchdog", "gomesh", "legacy")
_MAX_TELEGRAM_TEXT = 4096
_MAX_TELEGRAM_CAPTION = 1024
_MAX_UPDATE_BYTES = 1024 * 1024
_WEBHOOK_SECRET = re.compile(r"^[A-Za-z0-9_-]{32,256}$")
_IMAGE_ARTIFACT_PATH = re.compile(
    r"^/api/v1/artifacts/images/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)
_INSECURE_WEBHOOK_SECRETS = {
    "change-me",
    "changeme",
    "kolibri-webhook-secret",
    "secret",
    "telegram-webhook-secret",
}


def _enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in _TRUE


def _webhook_secret() -> str:
    return os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()


def _secret_is_valid(secret: str | None = None) -> bool:
    candidate = (secret if secret is not None else _webhook_secret()).strip()
    return bool(
        candidate
        and candidate.lower() not in _INSECURE_WEBHOOK_SECRETS
        and _WEBHOOK_SECRET.fullmatch(candidate)
    )


def _allowed_chat_ids() -> set[int]:
    raw = os.getenv("KOLIBRI_TELEGRAM_ALLOWED_CHAT_IDS", "")
    if not raw.strip():
        return set()
    result: set[int] = set()
    for item in raw.split(","):
        try:
            result.add(int(item.strip()))
        except (TypeError, ValueError):
            return set()
    return result


def _public_base_url() -> str | None:
    value = os.getenv("KOLIBRI_PUBLIC_BASE_URL", "").strip().rstrip("/")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        return None
    return value


def _readiness() -> dict[str, Any]:
    enabled = _enabled("KOLIBRI_TELEGRAM_WEBHOOK_ENABLED")
    owner_approved = _enabled("KOLIBRI_TELEGRAM_OWNER_APPROVED")
    secret_valid = _secret_is_valid()
    allowed_chat_count = len(_allowed_chat_ids())
    public_base_configured = _public_base_url() is not None
    live_delivery_verified = _enabled("KOLIBRI_TELEGRAM_LIVE_VERIFIED")
    blockers: list[str] = []
    if not enabled:
        blockers.append("webhook_disabled")
    if not owner_approved:
        blockers.append("owner_approval_required")
    if not secret_valid:
        blockers.append("protected_webhook_secret_required")
    if not allowed_chat_count:
        blockers.append("allowed_chat_ids_required")
    if not public_base_configured:
        blockers.append("public_https_base_url_required")
    if blockers:
        status = "disabled" if not enabled else "blocked"
    else:
        status = "ready" if live_delivery_verified else "configured_unverified"
    return {
        "status": status,
        "receiver_ready": not blockers,
        "owner_approved": owner_approved,
        "secret_valid": secret_valid,
        "allowed_chat_count": allowed_chat_count,
        "public_base_configured": public_base_configured,
        "live_delivery_verified": live_delivery_verified,
        "blockers": blockers,
    }


def _webhook_ready() -> bool:
    readiness = _readiness()
    return bool(readiness["receiver_ready"] and readiness["live_delivery_verified"])


def _verify_webhook(request: Request) -> None:
    """Require an explicitly enabled webhook and a non-default secret."""

    readiness = _readiness()
    if not _enabled("KOLIBRI_TELEGRAM_WEBHOOK_ENABLED"):
        raise HTTPException(status_code=503, detail={"code": "telegram_webhook_disabled"})
    if not _enabled("KOLIBRI_TELEGRAM_OWNER_APPROVED"):
        raise HTTPException(status_code=503, detail={"code": "telegram_owner_approval_required"})
    expected = _webhook_secret()
    if not _secret_is_valid(expected):
        raise HTTPException(status_code=503, detail={"code": "telegram_webhook_secret_invalid"})
    if not readiness["allowed_chat_count"]:
        raise HTTPException(status_code=503, detail={"code": "telegram_allowed_chats_not_configured"})
    if not readiness["public_base_configured"]:
        raise HTTPException(status_code=503, detail={"code": "telegram_public_base_not_configured"})
    supplied = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=403, detail={"code": "invalid_webhook_secret"})


def _reply(chat_id: int | str, text: str) -> dict[str, Any]:
    """Build a single plain-text Telegram webhook reply.

    Provider output is not interpreted as HTML.  This prevents malformed
    markup and provider-controlled tags from changing the message payload.
    """

    clean = text.strip() or "Исполнение не завершено. Повторите запрос."
    if len(clean) > _MAX_TELEGRAM_TEXT:
        clean = f"{clean[: _MAX_TELEGRAM_TEXT - 1].rstrip()}…"
    return {"method": "sendMessage", "chat_id": chat_id, "text": clean}


def _response_reply(
    chat_id: int,
    text: str,
    artifact: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return real image bytes by URL only for a verified artifact contract."""

    base_url = _public_base_url()
    if isinstance(artifact, dict) and base_url:
        path = str(artifact.get("url") or "")
        if (
            artifact.get("type") == "image"
            and _IMAGE_ARTIFACT_PATH.fullmatch(path)
            and str(artifact.get("mime_type") or "").startswith("image/")
            and isinstance(artifact.get("size_bytes"), int)
            and artifact["size_bytes"] > 0
            and _SHA256.fullmatch(str(artifact.get("sha256") or ""))
        ):
            caption = text.strip() or "Изображение создано и проверено."
            if len(caption) > _MAX_TELEGRAM_CAPTION:
                caption = f"{caption[: _MAX_TELEGRAM_CAPTION - 1].rstrip()}…"
            return {
                "method": "sendPhoto",
                "chat_id": chat_id,
                "photo": f"{base_url}{path}",
                "caption": caption,
            }
    return _reply(chat_id, text)


def _local_command(text: str) -> str | None:
    command = text.split(maxsplit=1)[0].split("@", 1)[0].lower() if text.startswith("/") else ""
    if command == "/start":
        return (
            "Колибри готова продолжить этот проект. Пишите задачу обычным языком: "
            "вопрос, исследование, документ, смета, изображение, код, сайт или автоматизация."
        )
    if command == "/help":
        return (
            "Опишите конечный результат обычным языком. Колибри сохранит диалог в этом проекте "
            "и направит задачу доступному исполнителю."
        )
    if command == "/status":
        return (
            "Telegram не подставляет фиктивные цифры. Подтверждённое состояние фабрики "
            "показывается в защищённом /control с временем и ссылками на доказательства."
        )
    return None


def _normalise_command(text: str) -> str:
    command = text.split(maxsplit=1)[0].split("@", 1)[0].lower() if text.startswith("/") else ""
    tail = text.split(maxsplit=1)[1].strip() if " " in text else ""
    if command == "/estimate":
        return tail or "Создай смету и сохрани редактируемый результат в текущем проекте."
    if command == "/document":
        return tail or "Создай документ и сохрани редактируемый результат в текущем проекте."
    return text


def _conversation(repo: ProjectHistoryRepository, project_id: str) -> list[dict[str, str]]:
    items = repo.list_messages(project_id, after=0, limit=500)["items"]
    return [
        {"role": str(item["role"]), "content": str(item["content"])}
        for item in items
        if item["role"] in {"user", "assistant"}
        and item["status"] == "completed"
        and str(item["content"]).strip()
    ]


async def _execute_update(body: dict[str, Any], db: Session) -> dict[str, Any]:
    update_id = body.get("update_id")
    if not isinstance(update_id, int) or update_id < 0:
        raise HTTPException(status_code=422, detail={"code": "invalid_telegram_update"})

    message = body.get("message") or body.get("edited_message")
    if not isinstance(message, dict):
        return {"ok": True}
    chat = message.get("chat")
    if not isinstance(chat, dict) or not isinstance(chat.get("id"), int):
        raise HTTPException(status_code=422, detail={"code": "invalid_telegram_chat"})
    chat_id = chat["id"]
    if chat_id not in _allowed_chat_ids():
        raise HTTPException(status_code=403, detail={"code": "telegram_chat_not_allowed"})
    text = message.get("text")
    if not isinstance(text, str) or not text.strip():
        return {"ok": True}
    text = text.strip()

    scope_id = f"telegram:{chat_id}"
    repo = ProjectHistoryRepository(db, scope_id)
    project, _ = repo.create_project(
        {
            "title": "Telegram",
            "metadata": {"channel": "telegram"},
        },
        f"telegram-chat:{chat_id}",
    )
    prompt = _normalise_command(text)
    try:
        repo.append_message(
            project["id"],
            {"role": "user", "content": prompt, "status": "completed", "metadata": {}},
            f"telegram-update:{update_id}:user",
        )
        placeholder, placeholder_created = repo.append_message(
            project["id"],
            {"role": "assistant", "content": "", "status": "pending", "metadata": {}},
            f"telegram-update:{update_id}:assistant",
        )
    except ProjectConflictError as exc:
        raise HTTPException(status_code=409, detail={"code": "telegram_update_conflict"}) from exc

    # Telegram retries the same update until it receives a 2xx.  Only the
    # request that created the durable placeholder may execute or send a
    # response.  Every retry is a side-effect-free acknowledgement.
    # A retry may legitimately recover a crash between committing the user
    # message and committing the placeholder.  Ownership therefore belongs to
    # the request that creates the placeholder, not necessarily the user row.
    if not placeholder_created:
        return {"ok": True, "duplicate": True}

    local = _local_command(text)
    if local is not None:
        repo.update_message(
            project["id"],
            placeholder["id"],
            {
                "content": local,
                "status": "completed",
                "metadata": {"response_id": f"telegram_local:{update_id}"},
            },
            f"telegram-update:{update_id}:terminal",
        )
        return _reply(chat_id, local)

    try:
        record = await execute_kolibri_response(
            ResponsesRequest(model="kolibri", input=_conversation(repo, project["id"])),
            idempotency_key=f"telegram:{update_id}:response",
        )
        response_id = str(record["id"])
        content = str(record.get("content") or "").strip()
        status = str(record.get("status") or "failed")
        artifact = record.get("artifact") if isinstance(record.get("artifact"), dict) else None
    except Exception:
        # Do not leak provider errors, local paths or stderr to Telegram.  The
        # failed durable placeholder is sufficient for operator diagnosis and
        # prevents Telegram retries from launching a second attempt.
        response_id = f"telegram_failed:{update_id}"
        content = ""
        status = "failed"
        artifact = None
    terminal_status = "completed" if status == "completed" and (content or artifact) else "failed"
    response_metadata: dict[str, Any] = {"response_id": response_id}
    if artifact:
        response_metadata["artifact"] = {
            "id": artifact.get("id"),
            "type": artifact.get("type"),
            "sha256": artifact.get("sha256"),
        }
    repo.update_message(
        project["id"],
        placeholder["id"],
        {
            "content": content,
            "status": terminal_status,
            "metadata": response_metadata,
        },
        f"telegram-update:{update_id}:terminal",
    )
    if terminal_status != "completed":
        content = "Исполнение не завершено. Повторите запрос — он будет направлен другому доступному исполнителю."
    return _response_reply(chat_id, content, artifact if terminal_status == "completed" else None)


@router.post("/webhook")
async def telegram_webhook(request: Request, db: Session = Depends(get_db)):
    _verify_webhook(request)
    declared_length = request.headers.get("content-length")
    if declared_length:
        try:
            if int(declared_length) > _MAX_UPDATE_BYTES:
                raise HTTPException(status_code=413, detail={"code": "telegram_update_too_large"})
        except ValueError as exc:
            raise HTTPException(status_code=400, detail={"code": "invalid_content_length"}) from exc
    raw_body = await request.body()
    if len(raw_body) > _MAX_UPDATE_BYTES:
        raise HTTPException(status_code=413, detail={"code": "telegram_update_too_large"})
    try:
        body = json.loads(raw_body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail={"code": "invalid_telegram_json"}) from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail={"code": "invalid_telegram_update"})
    return await _execute_update(body, db)


@router.get("/info")
async def bot_info():
    readiness = _readiness()
    return {
        "webhook_enabled": _enabled("KOLIBRI_TELEGRAM_WEBHOOK_ENABLED"),
        "webhook_ready": _webhook_ready(),
        "receiver_ready": readiness["receiver_ready"],
        "readiness": readiness,
        "bot_configured": bool(os.getenv("TELEGRAM_BOT_TOKEN", "").strip()),
        "execution_contract": "kolibri-responses",
        "history_contract": "project-history",
        "background_senders": {name: False for name in _BLOCKED_BACKGROUND_SENDERS},
        "background_sender_evidence": {
            "scope": "telegram-adapter-process",
            "fleet_runtime": "unknown",
        },
        "commands": [
            {"command": "start", "description": "Начать или продолжить проект"},
            {"command": "status", "description": "Где смотреть подтверждённый статус"},
            {"command": "estimate", "description": "Создать смету"},
            {"command": "document", "description": "Создать документ"},
            {"command": "help", "description": "Помощь"},
        ],
    }
