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
from dataclasses import dataclass
from datetime import datetime, timezone
from ipaddress import IPv4Address, IPv6Address, ip_address, ip_network
from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import TelegramDeliveryEvidenceDB
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
_DELIVERY_EVIDENCE_ID = "telegram-webhook-live"
_DEFAULT_DELIVERY_EVIDENCE_MAX_AGE_SECONDS = 24 * 60 * 60
_TELEGRAM_WEBHOOK_NETWORKS = tuple(
    ip_network(value)
    for value in (
        "149.154.160.0/20",
        "91.108.4.0/22",
    )
)
_LOOPBACK_PROXY_NETWORKS = (
    ip_network("127.0.0.0/8"),
    ip_network("::1/128"),
)


@dataclass(frozen=True)
class _WebhookOrigin:
    address: IPv4Address | IPv6Address | None
    official_network: str | None
    trusted_proxy_config_valid: bool


def _enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in _TRUE


def _delivery_evidence_max_age_seconds() -> int:
    raw = os.getenv("KOLIBRI_TELEGRAM_DELIVERY_EVIDENCE_MAX_AGE_SECONDS", "").strip()
    if not raw:
        return _DEFAULT_DELIVERY_EVIDENCE_MAX_AGE_SECONDS
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_DELIVERY_EVIDENCE_MAX_AGE_SECONDS
    return min(max(value, 60), 7 * 24 * 60 * 60)


def _trusted_proxy_networks() -> tuple[tuple[Any, ...], bool]:
    """Return an explicit, narrow proxy trust set.

    Loopback is trusted because the production ASGI service sits behind the
    Home nginx process.  Mesh relay addresses must be added explicitly as /32
    (or another narrow subnet) in the protected runtime configuration.  Broad
    trust ranges are rejected so an attacker cannot make a forged
    X-Forwarded-For value look like Telegram.
    """

    networks: list[Any] = list(_LOOPBACK_PROXY_NETWORKS)
    raw = os.getenv("KOLIBRI_TELEGRAM_TRUSTED_PROXY_CIDRS", "").strip()
    if not raw:
        return tuple(networks), True
    valid = True
    for item in raw.split(","):
        candidate = item.strip()
        if not candidate:
            valid = False
            continue
        try:
            network = ip_network(candidate, strict=False)
        except ValueError:
            valid = False
            continue
        minimum_prefix = 24 if network.version == 4 else 64
        if network.prefixlen < minimum_prefix:
            valid = False
            continue
        if any(network.overlaps(telegram) for telegram in _TELEGRAM_WEBHOOK_NETWORKS):
            valid = False
            continue
        networks.append(network)
    return tuple(networks), valid


def _in_networks(address: IPv4Address | IPv6Address, networks: tuple[Any, ...]) -> bool:
    return any(address.version == network.version and address in network for network in networks)


def _request_origin(request: Request) -> _WebhookOrigin:
    trusted, trusted_config_valid = _trusted_proxy_networks()
    peer_value = request.client.host if request.client is not None else ""
    try:
        peer = ip_address(peer_value)
    except ValueError:
        return _WebhookOrigin(None, None, trusted_config_valid)

    origin = peer
    if _in_networks(peer, trusted):
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            chain: list[IPv4Address | IPv6Address] = []
            for item in forwarded.split(","):
                try:
                    chain.append(ip_address(item.strip()))
                except ValueError:
                    return _WebhookOrigin(None, None, trusted_config_valid)
            chain.append(peer)
            index = len(chain) - 1
            while index >= 0 and _in_networks(chain[index], trusted):
                index -= 1
            if index < 0:
                return _WebhookOrigin(None, None, trusted_config_valid)
            origin = chain[index]

    official_network = next(
        (
            str(network)
            for network in _TELEGRAM_WEBHOOK_NETWORKS
            if origin.version == network.version and origin in network
        ),
        None,
    )
    return _WebhookOrigin(origin, official_network, trusted_config_valid)


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


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _delivery_evidence(db: Session | None) -> dict[str, Any]:
    max_age_seconds = _delivery_evidence_max_age_seconds()
    unavailable = {
        "status": "unavailable" if db is not None else "absent",
        "verified_at": None,
        "age_seconds": None,
        "max_age_seconds": max_age_seconds,
        "update_id": None,
        "response_method": None,
        "origin_network": None,
    }
    if db is None:
        return unavailable
    try:
        row = db.get(TelegramDeliveryEvidenceDB, _DELIVERY_EVIDENCE_ID)
    except SQLAlchemyError:
        db.rollback()
        return unavailable
    if row is None:
        return {
            "status": "absent",
            "verified_at": None,
            "age_seconds": None,
            "max_age_seconds": max_age_seconds,
            "update_id": None,
            "response_method": None,
            "origin_network": None,
        }
    verified_at = _utc(row.verified_at)
    age_seconds = max(0, int((datetime.now(timezone.utc) - verified_at).total_seconds()))
    return {
        "status": "current" if age_seconds <= max_age_seconds else "stale",
        "verified_at": verified_at.isoformat(),
        "age_seconds": age_seconds,
        "max_age_seconds": max_age_seconds,
        "update_id": row.update_id,
        "response_method": row.response_method,
        "origin_network": row.origin_network,
    }


def _readiness(db: Session | None = None) -> dict[str, Any]:
    enabled = _enabled("KOLIBRI_TELEGRAM_WEBHOOK_ENABLED")
    owner_approved = _enabled("KOLIBRI_TELEGRAM_OWNER_APPROVED")
    secret_valid = _secret_is_valid()
    allowed_chat_count = len(_allowed_chat_ids())
    public_base_configured = _public_base_url() is not None
    _, trusted_proxy_config_valid = _trusted_proxy_networks()
    require_official_source = _enabled("KOLIBRI_TELEGRAM_REQUIRE_OFFICIAL_SOURCE")
    evidence = _delivery_evidence(db)
    live_delivery_verified = evidence["status"] == "current"
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
    if require_official_source and not trusted_proxy_config_valid:
        blockers.append("trusted_proxy_cidrs_invalid")
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
        "require_official_source": require_official_source,
        "trusted_proxy_config_valid": trusted_proxy_config_valid,
        "live_delivery_verified": live_delivery_verified,
        "delivery_evidence": evidence,
        "blockers": blockers,
    }


def _webhook_ready(db: Session | None = None) -> bool:
    readiness = _readiness(db)
    return bool(readiness["receiver_ready"] and readiness["live_delivery_verified"])


def _verify_webhook(request: Request) -> _WebhookOrigin:
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
    origin = _request_origin(request)
    if _enabled("KOLIBRI_TELEGRAM_REQUIRE_OFFICIAL_SOURCE") and not origin.official_network:
        raise HTTPException(status_code=403, detail={"code": "telegram_origin_not_verified"})
    return origin


def _persist_delivery_evidence(
    db: Session,
    *,
    update_id: int,
    response_method: str,
    origin_network: str,
) -> bool:
    try:
        now = datetime.now(timezone.utc)
        row = db.get(TelegramDeliveryEvidenceDB, _DELIVERY_EVIDENCE_ID)
        if row is None:
            row = TelegramDeliveryEvidenceDB(
                id=_DELIVERY_EVIDENCE_ID,
                update_id=update_id,
                response_method=response_method,
                origin_network=origin_network,
                verified_at=now,
                updated_at=now,
            )
            db.add(row)
        else:
            row.update_id = update_id
            row.response_method = response_method
            row.origin_network = origin_network
            row.verified_at = now
            row.updated_at = now
        db.commit()
    except SQLAlchemyError:
        # Delivery of the user response is more important than the auxiliary
        # readiness snapshot.  A failed evidence write leaves readiness
        # partial and will be retried by the next valid Telegram update.
        db.rollback()
        return False
    return True


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
    origin = _verify_webhook(request)
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
    response = await _execute_update(body, db)
    update_id = body.get("update_id")
    if origin.official_network and isinstance(update_id, int) and update_id >= 0:
        method = str(response.get("method") or "ack") if isinstance(response, dict) else "ack"
        _persist_delivery_evidence(
            db,
            update_id=update_id,
            response_method=method,
            origin_network=origin.official_network,
        )
    return response


@router.get("/info")
async def bot_info(db: Session = Depends(get_db)):
    readiness = _readiness(db)
    return {
        "webhook_enabled": _enabled("KOLIBRI_TELEGRAM_WEBHOOK_ENABLED"),
        "webhook_ready": _webhook_ready(db),
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
