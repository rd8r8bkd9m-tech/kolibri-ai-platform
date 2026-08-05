"""User-managed AI models with encrypted API keys.

Allows non-admin users to add their own models from OpenAI, Anthropic, Qwen,
or custom OpenAI-compatible providers. Keys are encrypted with AES-256-GCM
using the same master key infrastructure as provider vault.
"""

from __future__ import annotations

import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any

import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag
from fastapi import APIRouter, Depends, HTTPException, Request, status

from .config import Settings
from .database import get_database, transaction
from .identity import require_user
from .local_provider_authority import (
    LocalProviderAuthorityError,
    ensure_local_provider_master_key,
)
from .schemas import UserSession

router = APIRouter(prefix="/v1/user-models", tags=["user-models"])

DatabaseDependency = Annotated[sqlite3.Connection, Depends(get_database)]
IdentityDependency = Annotated[UserSession, Depends(require_user)]

_PROVIDER_TYPES = {"openai", "anthropic", "qwen", "custom"}
_API_KEY = re.compile(r"^[\x21-\x7e]{16,8192}$")
_MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")
_DISPLAY_NAME = re.compile(r"^[\w\s\-\.]{1,80}$")
_BASE_URL = re.compile(r"^https?://[\w\.\-]+(:\d+)?(/[\w\.\-/]*)?$")

_PROVIDER_DEFAULTS = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
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
    tenant_id: str,
    user_id: str,
    model_id: str,
) -> bytes:
    """Encrypt an API key using AES-256-GCM with tenant/user-bound AAD."""
    master_key = ensure_local_provider_master_key(settings)
    nonce = os.urandom(12)
    aad = (
        f"kolibri-v3-user-model-v1\0{tenant_id}\0{user_id}\0{model_id}"
    ).encode("utf-8", "strict")
    ciphertext = AESGCM(master_key).encrypt(
        nonce,
        api_key.encode("utf-8", "strict"),
        aad,
    )
    return nonce + ciphertext  # Store nonce + ciphertext together


def _decrypt_api_key(
    settings: Settings,
    encrypted: bytes,
    *,
    tenant_id: str,
    user_id: str,
    model_id: str,
) -> str:
    """Decrypt an API key from stored nonce+ciphertext."""
    if len(encrypted) < 13:  # 12 bytes nonce + at least 1 byte ciphertext
        raise LocalProviderAuthorityError(
            "user_model_key_invalid",
            "Зашифрованный ключ имеет неверный формат.",
        )
    master_key = ensure_local_provider_master_key(settings)
    nonce = encrypted[:12]
    ciphertext = encrypted[12:]
    aad = (
        f"kolibri-v3-user-model-v1\0{tenant_id}\0{user_id}\0{model_id}"
    ).encode("utf-8", "strict")
    try:
        plaintext = AESGCM(master_key).decrypt(nonce, ciphertext, aad)
    except InvalidTag:
        raise LocalProviderAuthorityError(
            "user_model_key_invalid",
            "Не удалось расшифровать ключ модели.",
        ) from None
    return plaintext.decode("utf-8", "strict")


def _validate_api_key(api_key: str) -> str:
    """Validate API key format."""
    if not isinstance(api_key, str) or not _API_KEY.fullmatch(api_key):
        raise _error(
            status.HTTP_400_BAD_REQUEST,
            "user_model_api_key_invalid",
            "API-ключ должен содержать от 16 до 8192 printable ASCII символов.",
        )
    return api_key.strip()


def _validate_model_id(model_id: str) -> str:
    """Validate model ID format."""
    if not isinstance(model_id, str) or not _MODEL_ID.fullmatch(model_id):
        raise _error(
            status.HTTP_400_BAD_REQUEST,
            "user_model_id_invalid",
            "ID модели должен содержать только буквы, цифры, точки и дефисы.",
        )
    return model_id.strip()


def _validate_display_name(name: str) -> str:
    """Validate display name."""
    if not isinstance(name, str) or not _DISPLAY_NAME.fullmatch(name):
        raise _error(
            status.HTTP_400_BAD_REQUEST,
            "user_model_display_name_invalid",
            "Название модели должно содержать только буквы, цифры, пробелы и дефисы (макс. 80 символов).",
        )
    return name.strip()


def _validate_base_url(url: str | None, provider_type: str) -> str:
    """Validate base URL for custom providers."""
    if provider_type == "custom":
        if not url or not _BASE_URL.fullmatch(url):
            raise _error(
                status.HTTP_400_BAD_REQUEST,
                "user_model_base_url_invalid",
                "Для custom провайдера требуется корректный base URL (http/https).",
            )
        return url.rstrip("/")
    # For known providers, use defaults
    return _PROVIDER_DEFAULTS.get(provider_type, {}).get("base_url", "")


async def _test_provider_connection(
    provider_type: str,
    api_key: str,
    base_url: str,
    model_id: str,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """Test connection to a provider API."""
    defaults = _PROVIDER_DEFAULTS.get(provider_type, {})
    auth_header = defaults.get("auth_header", "Authorization")
    auth_prefix = defaults.get("auth_prefix", "Bearer ")

    headers = {
        "Accept": "application/json",
        auth_header: f"{auth_prefix}{api_key}",
    }

    # For custom providers, try to list models or make a minimal request
    if provider_type == "custom":
        test_url = f"{base_url}/models"
    else:
        test_url = f"{base_url}{defaults.get('models_endpoint', '/models')}"

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=5),
            follow_redirects=False,
            trust_env=False,
        ) as client:
            response = await client.get(test_url, headers=headers)
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
    except httpx.HTTPError as e:
        return {
            "status": "failed",
            "error": "http_error",
            "message": f"Ошибка HTTP: {str(e)}",
        }

    if response.status_code in {401, 403}:
        return {
            "status": "failed",
            "error": "auth_failed",
            "message": "API-ключ отклонён провайдером. Проверьте ключ.",
        }
    if response.status_code == 404:
        # Some providers don't have a models endpoint, try a minimal chat request
        return await _test_chat_completion(
            provider_type, api_key, base_url, model_id, timeout
        )
    if response.status_code != 200:
        return {
            "status": "failed",
            "error": "provider_error",
            "message": f"Провайдер вернул HTTP {response.status_code}.",
        }

    return {
        "status": "connected",
        "message": "Подключение успешно.",
    }


async def _test_chat_completion(
    provider_type: str,
    api_key: str,
    base_url: str,
    model_id: str,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """Test by making a minimal chat completion request."""
    defaults = _PROVIDER_DEFAULTS.get(provider_type, {})
    auth_header = defaults.get("auth_header", "Authorization")
    auth_prefix = defaults.get("auth_prefix", "Bearer ")

    headers = {
        "Content-Type": "application/json",
        auth_header: f"{auth_prefix}{api_key}",
    }

    # Different providers have different chat endpoints
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
        return {
            "status": "connected",
            "message": "Подключение успешно.",
        }
    return {
        "status": "failed",
        "error": "provider_error",
        "message": f"Провайдер вернул HTTP {response.status_code}.",
    }


@router.get("")
def list_user_models(
    database: DatabaseDependency,
    identity: IdentityDependency,
) -> dict[str, Any]:
    """List all user models for the current user."""
    rows = database.execute(
        """
        SELECT id, provider_type, provider_name, base_url, model_id,
               display_name, auto_priority, is_enabled,
               last_tested_at, last_test_status,
               created_at, updated_at
        FROM user_models
        WHERE tenant_id = ? AND user_id = ?
        ORDER BY auto_priority DESC, created_at DESC
        """,
        (identity.tenant_id, identity.user_id),
    ).fetchall()

    models = []
    for row in rows:
        models.append({
            "id": str(row["id"]),
            "providerType": str(row["provider_type"]),
            "providerName": str(row["provider_name"]),
            "baseUrl": str(row["base_url"]) if row["base_url"] else None,
            "modelId": str(row["model_id"]),
            "displayName": str(row["display_name"]),
            "autoPriority": int(row["auto_priority"]),
            "isEnabled": bool(row["is_enabled"]),
            "lastTestedAt": str(row["last_tested_at"]) if row["last_tested_at"] else None,
            "lastTestStatus": str(row["last_test_status"]) if row["last_test_status"] else None,
            "createdAt": str(row["created_at"]),
            "updatedAt": str(row["updated_at"]),
        })

    return {"models": models}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_user_model(
    request: Request,
    database: DatabaseDependency,
    identity: IdentityDependency,
) -> dict[str, Any]:
    """Add a new user model with encrypted API key."""
    settings: Settings = request.app.state.settings

    try:
        body = await request.json()
    except Exception:
        raise _error(
            status.HTTP_400_BAD_REQUEST,
            "user_model_body_invalid",
            "Тело запроса должно быть валидным JSON.",
        )

    provider_type = body.get("providerType", "").strip().lower()
    if provider_type not in _PROVIDER_TYPES:
        raise _error(
            status.HTTP_400_BAD_REQUEST,
            "user_model_provider_invalid",
            f"Провайдер должен быть одним из: {', '.join(sorted(_PROVIDER_TYPES))}.",
        )

    api_key = _validate_api_key(body.get("apiKey", ""))
    model_id = _validate_model_id(body.get("modelId", ""))
    display_name = _validate_display_name(body.get("displayName", ""))
    base_url = _validate_base_url(body.get("baseUrl"), provider_type)
    auto_priority = int(body.get("autoPriority", 50))
    if not 0 <= auto_priority <= 100:
        raise _error(
            status.HTTP_400_BAD_REQUEST,
            "user_model_priority_invalid",
            "Приоритет должен быть от 0 до 100.",
        )

    # Test connection before saving
    test_result = await _test_provider_connection(
        provider_type, api_key, base_url, model_id
    )
    if test_result["status"] != "connected":
        raise _error(
            status.HTTP_400_BAD_REQUEST,
            test_result.get("error", "user_model_connection_failed"),
            test_result.get("message", "Не удалось подключиться к провайдеру."),
        )

    # Encrypt the API key
    try:
        encrypted_key = _encrypt_api_key(
            settings,
            api_key,
            tenant_id=identity.tenant_id,
            user_id=identity.user_id,
            model_id=model_id,
        )
    except LocalProviderAuthorityError as e:
        raise _error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            e.code,
            e.message,
        ) from None

    # Save to database
    model_uuid = str(uuid.uuid4())
    now = _utc_now()
    provider_name = body.get("providerName", provider_type.capitalize())

    with transaction(database, immediate=True):
        database.execute(
            """
            INSERT INTO user_models (
                id, tenant_id, user_id, provider_type, provider_name,
                api_key_encrypted, base_url, model_id, display_name,
                auto_priority, is_enabled, last_tested_at, last_test_status,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
            """,
            (
                model_uuid,
                identity.tenant_id,
                identity.user_id,
                provider_type,
                provider_name,
                encrypted_key,
                base_url,
                model_id,
                display_name,
                auto_priority,
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
            "autoPriority": auto_priority,
            "isEnabled": True,
            "lastTestedAt": now,
            "lastTestStatus": "connected",
            "createdAt": now,
            "updatedAt": now,
        }
    }


@router.patch("/{model_id}")
async def update_user_model(
    model_id: str,
    request: Request,
    database: DatabaseDependency,
    identity: IdentityDependency,
) -> dict[str, Any]:
    """Update a user model (name, priority, enabled status)."""
    settings: Settings = request.app.state.settings

    # Verify ownership
    row = database.execute(
        """
        SELECT * FROM user_models
        WHERE tenant_id = ? AND user_id = ? AND id = ?
        """,
        (identity.tenant_id, identity.user_id, model_id),
    ).fetchone()

    if row is None:
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "user_model_not_found",
            "Модель не найдена.",
        )

    try:
        body = await request.json()
    except Exception:
        raise _error(
            status.HTTP_400_BAD_REQUEST,
            "user_model_body_invalid",
            "Тело запроса должно быть валидным JSON.",
        )

    updates = {}
    now = _utc_now()

    if "displayName" in body:
        updates["display_name"] = _validate_display_name(body["displayName"])
    if "autoPriority" in body:
        priority = int(body["autoPriority"])
        if not 0 <= priority <= 100:
            raise _error(
                status.HTTP_400_BAD_REQUEST,
                "user_model_priority_invalid",
                "Приоритет должен быть от 0 до 100.",
            )
        updates["auto_priority"] = priority
    if "isEnabled" in body:
        updates["is_enabled"] = 1 if body["isEnabled"] else 0
    if "apiKey" in body:
        # Re-encrypt new API key
        api_key = _validate_api_key(body["apiKey"])
        try:
            updates["api_key_encrypted"] = _encrypt_api_key(
                settings,
                api_key,
                tenant_id=identity.tenant_id,
                user_id=identity.user_id,
                model_id=str(row["model_id"]),
            )
        except LocalProviderAuthorityError as e:
            raise _error(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                e.code,
                e.message,
            ) from None

    if not updates:
        raise _error(
            status.HTTP_400_BAD_REQUEST,
            "user_model_no_updates",
            "Не указаны поля для обновления.",
        )

    updates["updated_at"] = now

    set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
    values = list(updates.values()) + [identity.tenant_id, identity.user_id, model_id]

    database.execute(
        f"""
        UPDATE user_models SET {set_clause}
        WHERE tenant_id = ? AND user_id = ? AND id = ?
        """,
        values,
    )

    # Return updated model
    updated_row = database.execute(
        """
        SELECT id, provider_type, provider_name, base_url, model_id,
               display_name, auto_priority, is_enabled,
               last_tested_at, last_test_status,
               created_at, updated_at
        FROM user_models
        WHERE tenant_id = ? AND user_id = ? AND id = ?
        """,
        (identity.tenant_id, identity.user_id, model_id),
    ).fetchone()

    return {
        "model": {
            "id": str(updated_row["id"]),
            "providerType": str(updated_row["provider_type"]),
            "providerName": str(updated_row["provider_name"]),
            "baseUrl": str(updated_row["base_url"]) if updated_row["base_url"] else None,
            "modelId": str(updated_row["model_id"]),
            "displayName": str(updated_row["display_name"]),
            "autoPriority": int(updated_row["auto_priority"]),
            "isEnabled": bool(updated_row["is_enabled"]),
            "lastTestedAt": str(updated_row["last_tested_at"]) if updated_row["last_tested_at"] else None,
            "lastTestStatus": str(updated_row["last_test_status"]) if updated_row["last_test_status"] else None,
            "createdAt": str(updated_row["created_at"]),
            "updatedAt": str(updated_row["updated_at"]),
        }
    }


@router.delete("/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user_model(
    model_id: str,
    database: DatabaseDependency,
    identity: IdentityDependency,
) -> None:
    """Delete a user model."""
    result = database.execute(
        """
        DELETE FROM user_models
        WHERE tenant_id = ? AND user_id = ? AND id = ?
        """,
        (identity.tenant_id, identity.user_id, model_id),
    )
    if result.rowcount == 0:
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "user_model_not_found",
            "Модель не найдена.",
        )


@router.post("/{model_id}/test")
async def test_user_model_connection(
    model_id: str,
    request: Request,
    database: DatabaseDependency,
    identity: IdentityDependency,
) -> dict[str, Any]:
    """Test connection to a user model."""
    settings: Settings = request.app.state.settings

    row = database.execute(
        """
        SELECT * FROM user_models
        WHERE tenant_id = ? AND user_id = ? AND id = ?
        """,
        (identity.tenant_id, identity.user_id, model_id),
    ).fetchone()

    if row is None:
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "user_model_not_found",
            "Модель не найдена.",
        )

    # Decrypt the API key
    try:
        api_key = _decrypt_api_key(
            settings,
            bytes(row["api_key_encrypted"]),
            tenant_id=identity.tenant_id,
            user_id=identity.user_id,
            model_id=str(row["model_id"]),
        )
    except LocalProviderAuthorityError as e:
        raise _error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            e.code,
            e.message,
        ) from None

    # Test connection
    test_result = await _test_provider_connection(
        str(row["provider_type"]),
        api_key,
        str(row["base_url"]) if row["base_url"] else _PROVIDER_DEFAULTS.get(str(row["provider_type"]), {}).get("base_url", ""),
        str(row["model_id"]),
    )

    # Update test status in DB
    now = _utc_now()
    database.execute(
        """
        UPDATE user_models
        SET last_tested_at = ?, last_test_status = ?, updated_at = ?
        WHERE tenant_id = ? AND user_id = ? AND id = ?
        """,
        (
            now,
            test_result["status"],
            now,
            identity.tenant_id,
            identity.user_id,
            model_id,
        ),
    )

    return test_result


__all__ = ["router"]
