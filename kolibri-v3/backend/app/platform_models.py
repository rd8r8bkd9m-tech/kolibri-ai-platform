"""Platform-wide AI models managed by the superadmin.

These models are available to all users with a shared API key, unlike
user_models which are per-user.  Keys are encrypted with AES-256-GCM
using the same master key infrastructure as provider vault.
"""

from __future__ import annotations

import json as _json
import ipaddress
import os
import re
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any
from urllib.parse import urlparse

import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag
from fastapi import APIRouter, Depends, HTTPException, Request, status

from .config import Settings
from .database import get_database, transaction
from .identity import require_owner
from .local_provider_authority import (
    LocalProviderAuthorityError,
    ensure_local_provider_master_key,
)
from .schemas import UserSession
from .security import require_mutation_auth

router = APIRouter(
    prefix="/v1/platform-admin/models",
    tags=["platform-admin-models"],
)

DatabaseDependency = Annotated[sqlite3.Connection, Depends(get_database)]
OwnerDependency = Annotated[UserSession, Depends(require_owner)]
MutationAuthDependency = Annotated[None, Depends(require_mutation_auth)]

_API_KEY_RE = re.compile(r"^[\x21-\x7e]{16,8192}$")
_MODEL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")
_DISPLAY_NAME_RE = re.compile(r"^[\w\s\-\.]{1,80}$")
_BASE_URL_RE = re.compile(r"^https?://[\w\.\-]+(:\d+)?(/[\w\.\-/]*)?$")
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._~-]{0,159}$")

_PROVIDER_DEFAULTS: dict[str, dict[str, str]] = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "models_endpoint": "/models",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "models_endpoint": "/models",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
    },
    "anthropic": {
        "base_url": "https://api.anthropic.com",
        "models_endpoint": "/v1/models",
        "auth_header": "x-api-key",
        "auth_prefix": "",
    },
    "qwen": {
        "base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "models_endpoint": "/models",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
    },
    "mimo": {
        "base_url": "https://token-plan-sgp.xiaomimimo.com/v1",
        "models_endpoint": "/models",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
    },
}


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _encrypt_api_key(
    settings: Settings,
    api_key: str,
    *,
    model_id: str,
) -> bytes:
    master_key = ensure_local_provider_master_key(settings)
    nonce = os.urandom(12)
    aad = f"kolibri-v3-platform-model-v1\0{model_id}".encode("utf-8", "strict")
    ciphertext = AESGCM(master_key).encrypt(
        nonce,
        api_key.encode("utf-8", "strict"),
        aad,
    )
    return nonce + ciphertext


def _decrypt_api_key(
    settings: Settings,
    encrypted: bytes,
    *,
    model_id: str,
) -> str:
    if len(encrypted) < 13:
        raise LocalProviderAuthorityError(
            "platform_model_key_invalid",
            "Зашифрованный ключ имеет неверный формат.",
        )
    master_key = ensure_local_provider_master_key(settings)
    nonce = encrypted[:12]
    ciphertext = encrypted[12:]
    aad = f"kolibri-v3-platform-model-v1\0{model_id}".encode("utf-8", "strict")
    try:
        plaintext = AESGCM(master_key).decrypt(nonce, ciphertext, aad)
    except InvalidTag:
        raise LocalProviderAuthorityError(
            "platform_model_key_invalid",
            "Не удалось расшифровать ключ модели.",
        ) from None
    return plaintext.decode("utf-8", "strict")


def _validate_api_key(api_key: str) -> str:
    if not isinstance(api_key, str) or not _API_KEY_RE.fullmatch(api_key):
        raise _error(
            status.HTTP_400_BAD_REQUEST,
            "platform_model_api_key_invalid",
            "API-ключ должен содержать от 16 до 8192 printable ASCII символов.",
        )
    return api_key.strip()


def _validate_model_id(model_id: str) -> str:
    if not isinstance(model_id, str) or not _MODEL_ID_RE.fullmatch(model_id):
        raise _error(
            status.HTTP_400_BAD_REQUEST,
            "platform_model_id_invalid",
            "ID модели должен содержать только буквы, цифры, точки и дефисы.",
        )
    return model_id.strip()


def _validate_display_name(name: str) -> str:
    if not isinstance(name, str) or not _DISPLAY_NAME_RE.fullmatch(name):
        raise _error(
            status.HTTP_400_BAD_REQUEST,
            "platform_model_display_name_invalid",
            "Название модели должно содержать только буквы, цифры, пробелы и дефисы (макс. 80 символов).",
        )
    return name.strip()


def _is_safe_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return False
        if hostname in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
            return False
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback:
                return False
        except ValueError:
            pass
        return True
    except Exception:
        return False

def _validate_base_url(url: str | None, provider_type: str) -> str:
    if provider_type == "custom":
        if not url or not _BASE_URL_RE.fullmatch(url):
            raise _error(
                status.HTTP_400_BAD_REQUEST,
                "platform_model_base_url_invalid",
                "Для custom провайдера требуется корректный base URL (http/https).",
            )
        if not _is_safe_url(url):
            raise _error(
                status.HTTP_400_BAD_REQUEST,
                "platform_model_base_url_ssrf",
                "Использование локальных или приватных адресов запрещено.",
            )
        return url.rstrip("/")
    return _PROVIDER_DEFAULTS.get(provider_type, {}).get("base_url", "")


def _row_to_payload(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "providerType": str(row["provider_type"]),
        "providerName": str(row["provider_name"]),
        "baseUrl": str(row["base_url"]) if row["base_url"] else None,
        "modelId": str(row["model_id"]),
        "displayName": str(row["display_name"]),
        "description": str(row["description"]) if row["description"] else "",
        "autoPriority": int(row["auto_priority"]),
        "isEnabled": bool(row["is_enabled"]),
        "isDefault": bool(row["is_default"]),
        "supportedReasoningEfforts": (
            _json.loads(row["supported_reasoning_efforts_json"])
            if row["supported_reasoning_efforts_json"]
            else []
        ),
        "serviceTiers": (
            _json.loads(row["service_tiers_json"])
            if row["service_tiers_json"]
            else []
        ),
        "lastTestedAt": (
            str(row["last_tested_at"]) if row["last_tested_at"] else None
        ),
        "lastTestStatus": (
            str(row["last_test_status"]) if row["last_test_status"] else None
        ),
        "createdAt": str(row["created_at"]),
        "updatedAt": str(row["updated_at"]),
    }


async def _test_provider_connection(
    provider_type: str,
    api_key: str,
    base_url: str,
    model_id: str,
    timeout: float = 10.0,
) -> dict[str, Any]:
    defaults = _PROVIDER_DEFAULTS.get(provider_type, {})
    auth_header = defaults.get("auth_header", "Authorization")
    auth_prefix = defaults.get("auth_prefix", "Bearer ")

    headers = {
        "Accept": "application/json",
        auth_header: f"{auth_prefix}{api_key}",
    }

    if provider_type == "custom":
        test_url = f"{base_url}/models"
    else:
        test_url = f"{base_url}{defaults.get('models_endpoint', '/models')}"

    start_time = time.monotonic()
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=5),
            follow_redirects=False,
            trust_env=False,
        ) as client:
            response = await client.get(test_url, headers=headers)
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
    except httpx.ConnectError:
        return {
            "status": "failed",
            "error": "connection_failed",
            "message": "Не удалось подключиться к API. Проверьте URL и сеть.",
        }
    except httpx.TimeoutException:
        return {
            "status": "failed",
            "error": "timeout",
            "message": "Превышено время ожидания ответа от API.",
        }
    except httpx.HTTPError as exc:
        return {
            "status": "failed",
            "error": "http_error",
            "message": f"Ошибка HTTP: {exc}",
        }

    if response.status_code in {401, 403}:
        return {
            "status": "failed",
            "error": "auth_failed",
            "message": f"API-ключ отклонён провайдером. Проверьте ключ. (Задержка: {elapsed_ms}ms)",
        }
    if response.status_code == 404:
        res = await _test_chat_completion(
            provider_type, api_key, base_url, model_id, timeout
        )
        if "message" in res and elapsed_ms:
            res["message"] += f" (Задержка: {elapsed_ms}ms)"
        return res
    if response.status_code != 200:
        return {
            "status": "failed",
            "error": "provider_error",
            "message": f"Провайдер вернул HTTP {response.status_code}. (Задержка: {elapsed_ms}ms)",
        }
    return {"status": "connected", "message": f"Подключение успешно. (Задержка: {elapsed_ms}ms)"}


async def _test_chat_completion(
    provider_type: str,
    api_key: str,
    base_url: str,
    model_id: str,
    timeout: float = 10.0,
) -> dict[str, Any]:
    defaults = _PROVIDER_DEFAULTS.get(provider_type, {})
    auth_header = defaults.get("auth_header", "Authorization")
    auth_prefix = defaults.get("auth_prefix", "Bearer ")

    headers = {
        "Content-Type": "application/json",
        auth_header: f"{auth_prefix}{api_key}",
    }

    if provider_type == "anthropic":
        chat_url = f"{base_url}/v1/messages"
        payload = {
            "model": model_id,
            "max_tokens": 10,
            "messages": [{"role": "user", "content": "Hi"}],
        }
    else:
        chat_url = f"{base_url}/chat/completions"
        payload = {
            "model": model_id,
            "max_tokens": 10,
            "messages": [{"role": "user", "content": "Hi"}],
        }

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=5),
            follow_redirects=False,
            trust_env=False,
        ) as client:
            response = await client.post(chat_url, headers=headers, json=payload)
    except httpx.ConnectError:
        return {
            "status": "failed",
            "error": "connection_failed",
            "message": "Не удалось подключиться к API.",
        }
    except httpx.TimeoutException:
        return {
            "status": "failed",
            "error": "timeout",
            "message": "Превышено время ожидания.",
        }

    if response.status_code in {401, 403}:
        return {
            "status": "failed",
            "error": "auth_failed",
            "message": "API-ключ отклонён.",
        }
    if response.status_code == 200:
        return {"status": "connected", "message": "Подключение успешно."}
    return {
        "status": "failed",
        "error": "provider_error",
        "message": f"Провайдер вернул HTTP {response.status_code}.",
    }


@router.get("")
def list_platform_models(
    _owner: OwnerDependency,
    database: DatabaseDependency,
) -> dict[str, Any]:
    rows = database.execute(
        """
        SELECT id, provider_type, provider_name, base_url, model_id,
               display_name, description, auto_priority, is_enabled,
               is_default, supported_reasoning_efforts_json,
               service_tiers_json, last_tested_at, last_test_status,
               created_at, updated_at
        FROM platform_models
        ORDER BY auto_priority DESC, created_at DESC
        """,
    ).fetchall()
    return {"models": [_row_to_payload(row) for row in rows]}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_platform_model(
    request: Request,
    _owner: OwnerDependency,
    _mutation: MutationAuthDependency,
    database: DatabaseDependency,
) -> dict[str, Any]:
    settings: Settings = request.app.state.settings

    try:
        body = await request.json()
    except Exception:
        raise _error(
            status.HTTP_400_BAD_REQUEST,
            "platform_model_body_invalid",
            "Тело запроса должно быть валидным JSON.",
        )

    provider_type = str(body.get("providerType", "")).strip().lower()
    if not provider_type:
        raise _error(
            status.HTTP_400_BAD_REQUEST,
            "platform_model_provider_invalid",
            "Тип провайдера обязателен.",
        )

    api_key = _validate_api_key(body.get("apiKey", ""))
    model_id = _validate_model_id(body.get("modelId", ""))
    display_name = _validate_display_name(body.get("displayName", ""))
    base_url = _validate_base_url(body.get("baseUrl"), provider_type)
    auto_priority = int(body.get("autoPriority", 50))
    if not 0 <= auto_priority <= 100:
        raise _error(
            status.HTTP_400_BAD_REQUEST,
            "platform_model_priority_invalid",
            "Приоритет должен быть от 0 до 100.",
        )

    test_result = await _test_provider_connection(
        provider_type, api_key, base_url, model_id
    )
    if test_result["status"] != "connected":
        raise _error(
            status.HTTP_400_BAD_REQUEST,
            test_result.get("error", "platform_model_connection_failed"),
            test_result.get("message", "Не удалось подключиться к провайдеру."),
        )

    try:
        encrypted_key = _encrypt_api_key(settings, api_key, model_id=model_id)
    except LocalProviderAuthorityError as exc:
        raise _error(status.HTTP_500_INTERNAL_SERVER_ERROR, exc.code, exc.message) from None

    model_uuid = str(uuid.uuid4())
    now = _utc_now()
    provider_name = body.get("providerName", provider_type.capitalize())
    description = str(body.get("description", "")).strip()[:1000]
    is_default = 1 if body.get("isDefault") else 0

    efforts_json = None
    if body.get("supportedReasoningEfforts"):
        efforts_json = _json.dumps(body["supportedReasoningEfforts"])

    tiers_json = None
    if body.get("serviceTiers"):
        tiers_json = _json.dumps(body["serviceTiers"])

    with transaction(database, immediate=True):
        database.execute(
            """
            INSERT INTO platform_models (
                id, provider_type, provider_name, api_key_encrypted,
                base_url, model_id, display_name, description,
                auto_priority, is_enabled, is_default,
                supported_reasoning_efforts_json, service_tiers_json,
                last_tested_at, last_test_status,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                model_uuid,
                provider_type,
                provider_name,
                encrypted_key,
                base_url if provider_type == "custom" else None,
                model_id,
                display_name,
                description,
                auto_priority,
                is_default,
                efforts_json,
                tiers_json,
                now,
                "connected",
                now,
                now,
            ),
        )

    return {
        "model": {
            "id": model_uuid,
            "providerType": provider_type,
            "providerName": provider_name,
            "baseUrl": base_url if provider_type == "custom" else None,
            "modelId": model_id,
            "displayName": display_name,
            "description": description,
            "autoPriority": auto_priority,
            "isEnabled": True,
            "isDefault": bool(is_default),
            "supportedReasoningEfforts": body.get("supportedReasoningEfforts", []),
            "serviceTiers": body.get("serviceTiers", []),
            "lastTestedAt": now,
            "lastTestStatus": "connected",
            "createdAt": now,
            "updatedAt": now,
        }
    }


@router.patch("/{model_id}")
async def update_platform_model(
    model_id: str,
    request: Request,
    _owner: OwnerDependency,
    _mutation: MutationAuthDependency,
    database: DatabaseDependency,
) -> dict[str, Any]:
    if not _SAFE_ID.fullmatch(model_id):
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "platform_model_not_found",
            "Модель не найдена.",
        )

    row = database.execute(
        "SELECT * FROM platform_models WHERE id = ?",
        (model_id,),
    ).fetchone()
    if row is None:
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "platform_model_not_found",
            "Модель не найдена.",
        )

    try:
        body = await request.json()
    except Exception:
        raise _error(
            status.HTTP_400_BAD_REQUEST,
            "platform_model_body_invalid",
            "Тело запроса должно быть валидным JSON.",
        )

    updates: dict[str, Any] = {}
    now = _utc_now()

    if "displayName" in body:
        updates["display_name"] = _validate_display_name(body["displayName"])
    if "description" in body:
        updates["description"] = str(body["description"]).strip()[:1000]
    if "autoPriority" in body:
        priority = int(body["autoPriority"])
        if not 0 <= priority <= 100:
            raise _error(
                status.HTTP_400_BAD_REQUEST,
                "platform_model_priority_invalid",
                "Приоритет должен быть от 0 до 100.",
            )
        updates["auto_priority"] = priority
    if "isEnabled" in body:
        updates["is_enabled"] = 1 if body["isEnabled"] else 0
    if "isDefault" in body:
        updates["is_default"] = 1 if body["isDefault"] else 0
    if "apiKey" in body:
        settings: Settings = request.app.state.settings
        api_key = _validate_api_key(body["apiKey"])
        try:
            updates["api_key_encrypted"] = _encrypt_api_key(
                settings, api_key, model_id=str(row["model_id"])
            )
        except LocalProviderAuthorityError as exc:
            raise _error(
                status.HTTP_500_INTERNAL_SERVER_ERROR, exc.code, exc.message
            ) from None

    if not updates:
        raise _error(
            status.HTTP_400_BAD_REQUEST,
            "platform_model_no_updates",
            "Не указаны поля для обновления.",
        )

    updates["updated_at"] = now

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [model_id]

    with transaction(database, immediate=True):
        database.execute(
            f"UPDATE platform_models SET {set_clause} WHERE id = ?",
            values,
        )

    updated_row = database.execute(
        "SELECT * FROM platform_models WHERE id = ?",
        (model_id,),
    ).fetchone()

    return {"model": _row_to_payload(updated_row)}


@router.delete("/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_platform_model(
    model_id: str,
    _owner: OwnerDependency,
    _mutation: MutationAuthDependency,
    database: DatabaseDependency,
) -> None:
    if not _SAFE_ID.fullmatch(model_id):
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "platform_model_not_found",
            "Модель не найдена.",
        )
    with transaction(database, immediate=True):
        result = database.execute(
            "DELETE FROM platform_models WHERE id = ?",
            (model_id,),
        )
    if result.rowcount == 0:
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "platform_model_not_found",
            "Модель не найдена.",
        )


@router.post("/{model_id}/test")
async def test_platform_model_connection(
    model_id: str,
    request: Request,
    _owner: OwnerDependency,
    _mutation: MutationAuthDependency,
    database: DatabaseDependency,
) -> dict[str, Any]:
    if not _SAFE_ID.fullmatch(model_id):
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "platform_model_not_found",
            "Модель не найдена.",
        )

    row = database.execute(
        "SELECT * FROM platform_models WHERE id = ?",
        (model_id,),
    ).fetchone()
    if row is None:
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "platform_model_not_found",
            "Модель не найдена.",
        )

    settings: Settings = request.app.state.settings
    try:
        api_key = _decrypt_api_key(
            settings,
            bytes(row["api_key_encrypted"]),
            model_id=str(row["model_id"]),
        )
    except LocalProviderAuthorityError as exc:
        raise _error(
            status.HTTP_500_INTERNAL_SERVER_ERROR, exc.code, exc.message
        ) from None

    base_url = (
        str(row["base_url"])
        if row["base_url"]
        else _PROVIDER_DEFAULTS.get(
            str(row["provider_type"]), {}
        ).get("base_url", "")
    )

    test_result = await _test_provider_connection(
        str(row["provider_type"]),
        api_key,
        base_url,
        str(row["model_id"]),
    )

    now = _utc_now()
    with transaction(database, immediate=True):
        database.execute(
            """
            UPDATE platform_models
            SET last_tested_at = ?, last_test_status = ?, updated_at = ?
            WHERE id = ?
            """,
            (now, test_result["status"], now, model_id),
        )

    return test_result


__all__ = ["router"]
