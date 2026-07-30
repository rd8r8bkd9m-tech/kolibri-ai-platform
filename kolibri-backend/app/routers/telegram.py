"""Telegram channel adapter for the canonical Kolibri response contract.

This module deliberately contains no polling loop, watchdog or GoMesh
reporter.  The webhook only authenticates and durably enqueues an update before
returning a fast 2xx.  A separate canonical worker executes the same Responses
service as ``POST /v1/responses`` and performs the only allowed Bot API sends.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import re
import socket
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from ipaddress import IPv4Address, IPv6Address, ip_address, ip_network
from typing import Any
from urllib.parse import quote, urlencode, urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.control_plane import (
    CONTROL_PLANE_SOURCE,
    ControlPlaneUnavailable,
    HomeControlPlaneAdapter,
)
from app.database import get_db
from app.models import (
    TelegramBotIdentityDB,
    TelegramDeliveryEvidenceDB,
    TelegramUpdateDB,
)
from app.project_history import ProjectConflictError, ProjectHistoryRepository
from app.project_handoff import ProjectHandoffError, issue_project_handoff
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
_DEFAULT_IDENTITY_EVIDENCE_MAX_AGE_SECONDS = 24 * 60 * 60
_DEFAULT_UPDATE_LEASE_SECONDS = 60 * 60
_DEFAULT_MAX_ATTEMPTS = 3
_BOT_IDENTITY_ID = "kolibriai-bot"
_EXPECTED_BOT_USERNAME = "kolibriai_bot"
_BOT_API_METHODS = frozenset({"getMe", "sendMessage", "editMessageText", "sendPhoto"})
_NETWORK_INTERFACE = re.compile(r"^[A-Za-z0-9_.:-]{1,15}$")
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
_FACTORY_STATUS_COMMAND = re.compile(r"^/status(?:@[a-z0-9_]+)?(?:\s|$)", re.IGNORECASE)
_FACTORY_STATUS_24_7 = re.compile(r"\b24\s*(?:/|x|х|на)\s*7\b", re.IGNORECASE)
_SAFE_CONTROL_PLANE_REASON = re.compile(r"^control_plane_[a-z0-9_]{1,64}$")


@dataclass(frozen=True)
class _WebhookOrigin:
    address: IPv4Address | IPv6Address | None
    official_network: str | None
    trusted_proxy_config_valid: bool


class TelegramWorkerError(RuntimeError):
    """Safe, classified Telegram worker failure without raw provider details."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


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


def _identity_evidence_max_age_seconds() -> int:
    raw = os.getenv("KOLIBRI_TELEGRAM_IDENTITY_EVIDENCE_MAX_AGE_SECONDS", "").strip()
    if not raw:
        return _DEFAULT_IDENTITY_EVIDENCE_MAX_AGE_SECONDS
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_IDENTITY_EVIDENCE_MAX_AGE_SECONDS
    return min(max(value, 60), 7 * 24 * 60 * 60)


def _update_lease_seconds() -> int:
    raw = os.getenv("KOLIBRI_TELEGRAM_UPDATE_LEASE_SECONDS", "").strip()
    try:
        value = int(raw) if raw else _DEFAULT_UPDATE_LEASE_SECONDS
    except ValueError:
        value = _DEFAULT_UPDATE_LEASE_SECONDS
    return min(max(value, 60), 6 * 60 * 60)


def _max_update_attempts() -> int:
    raw = os.getenv("KOLIBRI_TELEGRAM_MAX_ATTEMPTS", "").strip()
    try:
        value = int(raw) if raw else _DEFAULT_MAX_ATTEMPTS
    except ValueError:
        value = _DEFAULT_MAX_ATTEMPTS
    return min(max(value, 1), 10)


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


def _canonical_ingress(body: dict[str, Any]) -> dict[str, Any] | None:
    """Validate and minimise a Telegram update before durable persistence."""

    update_id = body.get("update_id")
    if not isinstance(update_id, int) or update_id < 0:
        raise HTTPException(status_code=422, detail={"code": "invalid_telegram_update"})
    message_kind = "message" if isinstance(body.get("message"), dict) else "edited_message"
    message = body.get("message") or body.get("edited_message")
    if not isinstance(message, dict):
        return None
    chat = message.get("chat")
    if not isinstance(chat, dict) or not isinstance(chat.get("id"), int):
        raise HTTPException(status_code=422, detail={"code": "invalid_telegram_chat"})
    chat_id = chat["id"]
    if chat_id not in _allowed_chat_ids():
        raise HTTPException(status_code=403, detail={"code": "telegram_chat_not_allowed"})
    text = message.get("text")
    if not isinstance(text, str) or not text.strip():
        return None
    message_id = message.get("message_id")
    if not isinstance(message_id, int) or message_id < 0:
        raise HTTPException(status_code=422, detail={"code": "invalid_telegram_message"})
    sender = message.get("from") if isinstance(message.get("from"), dict) else {}
    sender_id = sender.get("id") if isinstance(sender.get("id"), int) else None
    return {
        "update_id": update_id,
        "chat_id": chat_id,
        "message_id": message_id,
        "message_kind": message_kind,
        "sender_id": sender_id,
        "text": text.strip(),
    }


def _payload_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _persist_ingress(db: Session, payload: dict[str, Any]) -> tuple[TelegramUpdateDB, bool]:
    """Insert one update or return its exact idempotent replay."""

    fingerprint = _payload_hash(payload)
    existing = db.query(TelegramUpdateDB).filter(
        TelegramUpdateDB.update_id == payload["update_id"]
    ).first()
    if existing is not None:
        if not hmac.compare_digest(existing.payload_hash, fingerprint):
            raise HTTPException(status_code=409, detail={"code": "telegram_update_conflict"})
        return existing, False

    row = TelegramUpdateDB(
        id=str(uuid.uuid4()),
        update_id=payload["update_id"],
        chat_id=str(payload["chat_id"]),
        message_id=payload["message_id"],
        payload_hash=fingerprint,
        payload=payload,
        state="queued",
        attempts=0,
        outbound_state="pending",
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.query(TelegramUpdateDB).filter(
            TelegramUpdateDB.update_id == payload["update_id"]
        ).first()
        if existing is None or not hmac.compare_digest(existing.payload_hash, fingerprint):
            raise HTTPException(status_code=409, detail={"code": "telegram_update_conflict"})
        return existing, False
    db.refresh(row)
    return row, True


def _identity_evidence(db: Session | None) -> dict[str, Any]:
    max_age_seconds = _identity_evidence_max_age_seconds()
    absent = {
        "status": "absent" if db is None else "unavailable",
        "expected_username": _EXPECTED_BOT_USERNAME,
        "username": None,
        "verified": False,
        "verified_at": None,
        "age_seconds": None,
        "max_age_seconds": max_age_seconds,
    }
    if db is None:
        return absent
    try:
        row = db.get(TelegramBotIdentityDB, _BOT_IDENTITY_ID)
    except SQLAlchemyError:
        db.rollback()
        return absent
    if row is None:
        return {**absent, "status": "absent"}
    verified_at = _utc(row.verified_at)
    age_seconds = (
        max(0, int((datetime.now(timezone.utc) - verified_at).total_seconds()))
        if verified_at else None
    )
    current = bool(row.verified and age_seconds is not None and age_seconds <= max_age_seconds)
    return {
        "status": "current" if current else "stale" if row.verified else "mismatch",
        "expected_username": _EXPECTED_BOT_USERNAME,
        "username": row.username,
        "verified": current,
        "verified_at": verified_at.isoformat() if verified_at else None,
        "age_seconds": age_seconds,
        "max_age_seconds": max_age_seconds,
    }


def _bot_token() -> str:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise TelegramWorkerError("telegram_bot_token_missing")
    return token


async def _bot_api(method: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Call one allowlisted Bot API method without exposing credential URLs."""

    if method not in _BOT_API_METHODS:
        raise TelegramWorkerError("telegram_bot_method_forbidden")
    token = _bot_token()
    interface = os.getenv("KOLIBRI_TELEGRAM_EGRESS_INTERFACE", "").strip()
    try:
        if interface:
            if not _NETWORK_INTERFACE.fullmatch(interface):
                raise TelegramWorkerError("telegram_egress_interface_invalid")
            socket.if_nametoindex(interface)
            # curl is used only for the explicitly configured interface route.
            # The Bot token is imported from the inherited environment and
            # expanded inside curl, so it never appears in argv, logs or an
            # intermediate file.  The request JSON is delivered over stdin.
            process = await asyncio.create_subprocess_exec(
                "/usr/bin/curl",
                "--silent",
                "--show-error",
                "--max-time",
                "15",
                "--connect-timeout",
                "5",
                "--noproxy",
                "*",
                "--ipv4",
                "--interface",
                interface,
                "--variable",
                "%TELEGRAM_BOT_TOKEN",
                "--expand-url",
                f"https://api.telegram.org/bot{{{{TELEGRAM_BOT_TOKEN}}}}/{method}",
                "--header",
                "Content-Type: application/x-www-form-urlencoded",
                "--data-binary",
                "@-",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            form_payload = {
                key: json.dumps(value, ensure_ascii=False, separators=(",", ":"))
                if isinstance(value, (dict, list))
                else str(value)
                for key, value in payload.items()
                if value is not None
            }
            stdout, _stderr = await process.communicate(
                urlencode(form_payload).encode("utf-8")
            )
            if process.returncode != 0:
                raise TelegramWorkerError("telegram_bot_api_unavailable")
            response_status = 200
            data = json.loads(stdout)
        else:
            url = f"https://api.telegram.org/bot{token}/{method}"
            async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0)) as client:
                response = await client.post(url, json=payload)
            response_status = response.status_code
            data = response.json()
    except TelegramWorkerError:
        raise
    except Exception:
        raise TelegramWorkerError("telegram_bot_api_unavailable") from None
    if (
        response_status >= 400
        or not isinstance(data, dict)
        or data.get("ok") is not True
        or not isinstance(data.get("result"), dict)
    ):
        description = str(data.get("description") or "") if isinstance(data, dict) else ""
        if method == "editMessageText" and "message is not modified" in description.lower():
            return {}
        raise TelegramWorkerError("telegram_bot_api_rejected")
    return data["result"]


async def verify_bot_identity(db: Session) -> dict[str, Any]:
    """Persist sanitised ``getMe`` evidence and reject every non-canonical bot."""

    result = await _bot_api("getMe", {})
    username = str(result.get("username") or "")
    bot_id = result.get("id")
    verified = username.lower() == _EXPECTED_BOT_USERNAME and isinstance(bot_id, int)
    now = datetime.now(timezone.utc)
    row = db.get(TelegramBotIdentityDB, _BOT_IDENTITY_ID)
    if row is None:
        row = TelegramBotIdentityDB(id=_BOT_IDENTITY_ID)
        db.add(row)
    row.bot_id = str(bot_id) if isinstance(bot_id, int) else None
    row.username = username or None
    row.verified = verified
    row.verified_at = now
    row.updated_at = now
    db.commit()
    evidence = _identity_evidence(db)
    if not verified:
        raise TelegramWorkerError("telegram_bot_identity_mismatch")
    return evidence


def claim_next_update(db: Session, worker_id: str) -> str | None:
    """Fence one queued or lease-expired update for a single worker."""

    now = datetime.now(timezone.utc)
    query = db.query(TelegramUpdateDB).filter(
        or_(
            TelegramUpdateDB.state.in_(("queued", "retry")),
            and_(
                TelegramUpdateDB.state == "processing",
                TelegramUpdateDB.lease_until.is_not(None),
                TelegramUpdateDB.lease_until < now,
            ),
        ),
        TelegramUpdateDB.attempts < _max_update_attempts(),
    ).order_by(TelegramUpdateDB.created_at, TelegramUpdateDB.id)
    if db.bind is not None and db.bind.dialect.name != "sqlite":
        query = query.with_for_update(skip_locked=True)
    row = query.first()
    if row is None:
        return None
    row.state = "processing"
    row.attempts += 1
    row.lease_owner = worker_id
    row.lease_until = now + timedelta(seconds=_update_lease_seconds())
    row.last_error_code = None
    row.updated_at = now
    db.commit()
    return str(row.id)


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

    photo_url = _verified_image_photo_url(artifact)
    if photo_url:
        caption = text.strip() or "Изображение создано и проверено."
        if len(caption) > _MAX_TELEGRAM_CAPTION:
            caption = f"{caption[: _MAX_TELEGRAM_CAPTION - 1].rstrip()}…"
        return {
            "method": "sendPhoto",
            "chat_id": chat_id,
            "photo": photo_url,
            "caption": caption,
        }
    return _reply(chat_id, text)


def _verified_image_photo_url(artifact: dict[str, Any] | None) -> str | None:
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
            return f"{base_url}{path}"
    return None


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


def _is_factory_status_request(text: str) -> bool:
    """Recognise owner status questions without turning general factory work into a probe."""

    clean = " ".join(text.casefold().replace("ё", "е").split())
    if _FACTORY_STATUS_COMMAND.match(clean):
        return True
    has_factory = "фабрик" in clean or "kolibri factory" in clean
    if has_factory and re.search(r"\b(?:статус|состояние)\b", clean):
        return True
    if has_factory and re.search(
        r"\b(?:работает|работать|заработает|заработала|запущена|запущен|активна|активен)\b",
        clean,
    ):
        return True
    if _FACTORY_STATUS_24_7.search(clean):
        without_punctuation = re.sub(r"[^0-9a-zа-я/х ]+", " ", clean)
        compact = " ".join(without_punctuation.split())
        return has_factory or compact in {"24/7", "24 х 7", "24 x 7", "24 на 7"}
    return False


def _home_control_plane_adapter() -> HomeControlPlaneAdapter:
    return HomeControlPlaneAdapter.from_environment()


def _factory_status_group(
    stats: dict[str, Any],
    name: str,
    fields: tuple[str, ...],
) -> dict[str, int]:
    group = stats.get(name)
    if not isinstance(group, dict):
        raise ControlPlaneUnavailable("control_plane_status_contract_invalid")
    result: dict[str, int] = {}
    for field in fields:
        value = group.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ControlPlaneUnavailable("control_plane_status_contract_invalid")
        result[field] = value
    return result


def _factory_status_content(stats: dict[str, Any]) -> str:
    truth = stats.get("truth")
    if not isinstance(truth, dict):
        raise ControlPlaneUnavailable("control_plane_status_contract_invalid")
    availability = truth.get("availability")
    source = truth.get("source")
    raw_as_of = truth.get("as_of")
    if availability not in {"live", "stale"} or source != CONTROL_PLANE_SOURCE:
        raise ControlPlaneUnavailable("control_plane_status_contract_invalid")
    if not isinstance(raw_as_of, str) or not raw_as_of.strip():
        raise ControlPlaneUnavailable("control_plane_status_contract_invalid")
    try:
        parsed_as_of = datetime.fromisoformat(raw_as_of.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ControlPlaneUnavailable("control_plane_status_contract_invalid") from exc
    if parsed_as_of.tzinfo is None:
        raise ControlPlaneUnavailable("control_plane_status_contract_invalid")
    as_of = parsed_as_of.astimezone(timezone.utc).isoformat()

    nodes = _factory_status_group(
        stats,
        "nodes",
        ("total", "healthy", "degraded", "offline"),
    )
    agents = _factory_status_group(
        stats,
        "agents",
        ("total", "active", "idle", "paused"),
    )
    tasks = _factory_status_group(
        stats,
        "tasks",
        ("total", "running", "queued", "completed", "failed", "cancelled"),
    )
    return (
        "Фабрика Kolibri — инструментальный снимок Home Control Plane\n"
        f"Доступность: {availability}\n"
        f"as_of: {as_of}\n"
        f"Узлы: всего {nodes['total']}; исправны {nodes['healthy']}; "
        f"деградировали {nodes['degraded']}; недоступны {nodes['offline']}\n"
        f"Исполнители: всего {agents['total']}; активны {agents['active']}; "
        f"ожидают {agents['idle']}; приостановлены {agents['paused']}\n"
        f"Задачи: всего {tasks['total']}; выполняются {tasks['running']}; "
        f"в очереди {tasks['queued']}; завершены {tasks['completed']}; "
        f"ошибки {tasks['failed']}; отменены {tasks['cancelled']}\n"
        "Непрерывность 24/7 одним снимком не подтверждается."
    )


def _factory_status_unavailable(reason: str) -> str:
    safe_reason = (
        reason
        if _SAFE_CONTROL_PLANE_REASON.fullmatch(reason)
        else "control_plane_unavailable"
    )
    return (
        "Недоступно в текущем сеансе: подтверждённое состояние фабрики. "
        f"Причина: {safe_reason}. "
        "Могу вместо этого: повторить инструментальную проверку после восстановления "
        "Home Control Plane."
    )


async def _factory_status_reply() -> str:
    try:
        stats = await _home_control_plane_adapter().cluster_stats()
        return _factory_status_content(stats)
    except ControlPlaneUnavailable as exc:
        return _factory_status_unavailable(exc.reason)
    except Exception:
        return _factory_status_unavailable("control_plane_unavailable")


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


def _project_link(
    db: Session,
    *,
    project_id: str,
    source_scope_id: str,
    idempotency_key: str,
) -> str:
    base_url = _public_base_url()
    if not base_url:
        return ""
    try:
        # A bearer magic link is allowed only in a private Telegram chat.
        # Group continuity requires verified Telegram WebApp initData instead
        # of a forwardable link, so groups receive no broken project URL.
        chat_id = int(source_scope_id.split(":", 1)[1])
        if chat_id <= 0:
            return ""
        token = issue_project_handoff(
            db,
            project_id=project_id,
            source_scope_id=source_scope_id,
            idempotency_key=idempotency_key,
        )
    except (ProjectHandoffError, ValueError, IndexError):
        return ""
    return (
        f"{base_url}/app?project={quote(project_id, safe='')}"
        f"#handoff={quote(token, safe='')}"
    )


def _with_project_link(
    text: str,
    project_id: str,
    *,
    db: Session,
    source_scope_id: str,
    idempotency_key: str,
    maximum_length: int = _MAX_TELEGRAM_TEXT,
) -> str:
    link = _project_link(
        db,
        project_id=project_id,
        source_scope_id=source_scope_id,
        idempotency_key=idempotency_key,
    )
    clean = text.strip()
    if not link:
        return clean
    suffix = f"Открыть проект в Колибри: {link}"
    maximum = maximum_length - len(suffix) - 2
    if len(clean) > maximum:
        clean = f"{clean[: max(0, maximum - 1)].rstrip()}…"
    return f"{clean}\n\n{suffix}" if clean else suffix


async def _send_acknowledgement(row: TelegramUpdateDB, db: Session) -> None:
    if row.acknowledgement_message_id is not None:
        return
    result = await _bot_api(
        "sendMessage",
        {"chat_id": int(row.chat_id), "text": "Принято. Выполняю задачу…"},
    )
    message_id = result.get("message_id")
    if not isinstance(message_id, int):
        raise TelegramWorkerError("telegram_ack_missing_message_id")
    row.acknowledgement_message_id = message_id
    row.outbound_state = "acknowledged"
    row.updated_at = datetime.now(timezone.utc)
    db.commit()


async def _deliver_result(
    row: TelegramUpdateDB,
    db: Session,
    *,
    content: str,
    artifact: dict[str, Any] | None,
    include_project_link: bool = True,
) -> str:
    if row.outbound_state == "delivered":
        return str(row.delivery_method or "deduplicated")
    chat_id = int(row.chat_id)
    linked_content = content.strip()
    if include_project_link:
        linked_content = _with_project_link(
            content,
            str(row.project_id or ""),
            db=db,
            source_scope_id=f"telegram:{chat_id}",
            idempotency_key=f"telegram-update:{row.update_id}:project-handoff",
            maximum_length=(
                _MAX_TELEGRAM_CAPTION
                if _verified_image_photo_url(artifact)
                else _MAX_TELEGRAM_TEXT
            ),
        )
    reply = _response_reply(chat_id, linked_content, artifact)
    method = str(reply.pop("method"))
    if method == "sendMessage" and row.acknowledgement_message_id is not None:
        method = "editMessageText"
        reply["message_id"] = row.acknowledgement_message_id
    row.outbound_state = "delivery_started"
    row.delivery_method = method
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    result = await _bot_api(method, reply)
    result_message_id = result.get("message_id") if isinstance(result, dict) else None
    if isinstance(result_message_id, int):
        row.result_message_id = result_message_id
    row.outbound_state = "delivered"
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    return method


async def process_claimed_update(db: Session, update_row_id: str, worker_id: str) -> dict[str, Any]:
    """Execute one fenced update through the canonical Responses service."""

    row = db.get(TelegramUpdateDB, update_row_id)
    now = datetime.now(timezone.utc)
    if (
        row is None
        or row.state != "processing"
        or row.lease_owner != worker_id
        or _utc(row.lease_until) is None
        or _utc(row.lease_until) <= now
    ):
        raise TelegramWorkerError("telegram_update_lease_invalid")
    identity = _identity_evidence(db)
    if identity["verified"] is not True:
        raise TelegramWorkerError("telegram_bot_identity_unverified")

    payload = dict(row.payload or {})
    update_id = int(payload["update_id"])
    chat_id = int(payload["chat_id"])
    text = str(payload["text"])
    scope_id = f"telegram:{chat_id}"
    repo = ProjectHistoryRepository(db, scope_id)
    project, _ = repo.create_project(
        {"title": "Telegram", "metadata": {"channel": "telegram"}},
        f"telegram-chat:{chat_id}",
    )
    prompt = _normalise_command(text)
    try:
        repo.append_message(
            project["id"],
            {"role": "user", "content": prompt, "status": "completed", "metadata": {}},
            f"telegram-update:{update_id}:user",
        )
        placeholder, _ = repo.append_message(
            project["id"],
            {"role": "assistant", "content": "", "status": "pending", "metadata": {}},
            f"telegram-update:{update_id}:assistant",
        )
    except ProjectConflictError as exc:
        raise TelegramWorkerError("telegram_update_conflict") from exc
    row = db.get(TelegramUpdateDB, update_row_id)
    row.project_id = project["id"]
    row.assistant_message_id = placeholder["id"]
    row.updated_at = datetime.now(timezone.utc)
    db.commit()

    await _send_acknowledgement(row, db)
    factory_status_request = chat_id > 0 and _is_factory_status_request(text)
    local = None if factory_status_request else _local_command(text)
    artifact: dict[str, Any] | None = None
    if factory_status_request:
        response_id = f"telegram_factory_status:{update_id}"
        content = await _factory_status_reply()
        response_status = "completed"
    elif local is not None:
        response_id = f"telegram_local:{update_id}"
        content = local
        response_status = "completed"
    else:
        try:
            record = await execute_kolibri_response(
                ResponsesRequest(model="kolibri", input=_conversation(repo, project["id"])),
                idempotency_key=f"telegram:{update_id}:response",
                owner_scope=scope_id,
            )
            response_id = str(record["id"])
            content = str(record.get("content") or "").strip()
            response_status = str(record.get("status") or "failed")
            artifact = record.get("artifact") if isinstance(record.get("artifact"), dict) else None
        except Exception:
            response_id = f"telegram_failed:{update_id}"
            content = ""
            response_status = "failed"
            artifact = None
    terminal_status = (
        "completed"
        if response_status == "completed" and (content or artifact)
        else "failed"
    )
    response_metadata: dict[str, Any] = {
        "response_id": response_id,
        "channel": "telegram",
    }
    if artifact:
        response_metadata["artifact"] = {
            "id": artifact.get("id"),
            "type": artifact.get("type"),
            "sha256": artifact.get("sha256"),
        }
    repo.update_message(
        project["id"],
        placeholder["id"],
        {"content": content, "status": terminal_status, "metadata": response_metadata},
        f"telegram-update:{update_id}:terminal",
    )
    if terminal_status != "completed":
        content = (
            "Исполнение не завершено. Повторите запрос — он будет направлен "
            "другому доступному исполнителю."
        )
        artifact = None
    row = db.get(TelegramUpdateDB, update_row_id)
    row.response_id = response_id
    method = await _deliver_result(
        row,
        db,
        content=content,
        artifact=artifact,
        include_project_link=not factory_status_request,
    )
    row = db.get(TelegramUpdateDB, update_row_id)
    row.state = "completed"
    row.lease_owner = None
    row.lease_until = None
    row.last_error_code = None
    row.completed_at = datetime.now(timezone.utc)
    row.updated_at = row.completed_at
    db.commit()
    return {
        "update_id": update_id,
        "project_id": project["id"],
        "response_id": response_id,
        "delivery_method": method,
        "status": "completed",
    }


def mark_update_failure(db: Session, update_row_id: str, worker_id: str, code: str) -> None:
    row = db.get(TelegramUpdateDB, update_row_id)
    if row is None or row.lease_owner != worker_id or row.state != "processing":
        return
    row.state = "failed" if row.attempts >= _max_update_attempts() else "retry"
    row.lease_owner = None
    row.lease_until = None
    row.last_error_code = code[:120]
    row.updated_at = datetime.now(timezone.utc)
    db.commit()


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
    payload = _canonical_ingress(body)
    if payload is None:
        return {"ok": True, "accepted": False, "ignored": True}
    row, created = _persist_ingress(db, payload)
    update_id = payload["update_id"]
    if origin.official_network and isinstance(update_id, int) and update_id >= 0:
        _persist_delivery_evidence(
            db,
            update_id=update_id,
            response_method="async_ack",
            origin_network=origin.official_network,
        )
    return {
        "ok": True,
        "accepted": created,
        "duplicate": not created,
        "update_id": row.update_id,
    }


@router.get("/info")
async def bot_info(db: Session = Depends(get_db)):
    readiness = _readiness(db)
    identity = _identity_evidence(db)
    try:
        queue = {
            state: db.query(TelegramUpdateDB).filter(TelegramUpdateDB.state == state).count()
            for state in ("queued", "processing", "retry", "completed", "failed")
        }
    except SQLAlchemyError:
        db.rollback()
        queue = {state: None for state in ("queued", "processing", "retry", "completed", "failed")}
    return {
        "webhook_enabled": _enabled("KOLIBRI_TELEGRAM_WEBHOOK_ENABLED"),
        "webhook_ready": _webhook_ready(db),
        "receiver_ready": readiness["receiver_ready"],
        "readiness": readiness,
        "bot_configured": identity["verified"],
        "bot_identity": identity,
        "execution_contract": "v1-responses",
        "history_contract": "project-history",
        "ingress_contract": "durable-async-update-v1",
        "queue": queue,
        "background_senders": {name: False for name in _BLOCKED_BACKGROUND_SENDERS},
        "background_sender_evidence": {
            "scope": "telegram-adapter-process",
            "fleet_runtime": "unknown",
        },
        "outbound_worker": {
            "kind": "canonical-telegram-worker",
            "dedupe_key": "update_id",
            "acknowledgement": "sendMessage",
            "terminal_text": "editMessageText",
        },
        "commands": [
            {"command": "start", "description": "Начать или продолжить проект"},
            {"command": "status", "description": "Где смотреть подтверждённый статус"},
            {"command": "estimate", "description": "Создать смету"},
            {"command": "document", "description": "Создать документ"},
            {"command": "help", "description": "Помощь"},
        ],
    }
