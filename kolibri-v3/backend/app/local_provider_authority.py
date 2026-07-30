"""Local-development provider credential binding.

Production credentials belong to Provider Execution Authority on Primary.
This adapter exists only for the loopback V3 development runtime: it installs
MiMo's credential in the exact private CLI file and verifies the existing
Codex CLI login without returning or persisting secret material in Product DB.
"""

from __future__ import annotations

import hashlib
import base64
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag

from .config import Settings


_API_KEY = re.compile(r"^[\x21-\x7e]{16,8192}$")


class LocalProviderAuthorityError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code)
        self.code = code
        self.message = message


def _require_development(settings: Settings) -> None:
    if settings.environment != "development":
        raise LocalProviderAuthorityError(
            "local_provider_authority_disabled",
            "Локальная установка ключей отключена в этой среде.",
        )


def _require_vault_read(settings: Settings) -> None:
    if (
        settings.environment != "development"
        and not settings.local_provider_vault_read_enabled
    ):
        raise LocalProviderAuthorityError(
            "local_provider_authority_disabled",
            "Локальное хранилище ключей отключено в этой среде.",
        )


def _private_key_path(settings: Settings) -> Path:
    configured = os.getenv(
        "KOLIBRI_V3_PROVIDER_ENCRYPTION_KEY_FILE",
        "",
    ).strip()
    if configured:
        path = Path(configured)
    else:
        database_path = Path(
            settings.database_url.removeprefix("sqlite:///")
        )
        path = database_path.parent / ".kolibri-v3-provider-master-key"
    return path if path.is_absolute() else (Path.cwd() / path).resolve()


def _read_local_provider_master_key(
    settings: Settings,
    *,
    create_missing: bool,
) -> bytes:
    path = _private_key_path(settings)
    if create_missing:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    read_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, read_flags)
    except FileNotFoundError:
        if not create_missing:
            raise LocalProviderAuthorityError(
                "provider_master_key_missing",
                "Ключ шифрования provider-authority не настроен.",
            ) from None
        create_flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
        )
        try:
            descriptor = os.open(path, create_flags, 0o600)
        except FileExistsError:
            descriptor = os.open(path, read_flags)
        else:
            candidate = os.urandom(32)
            try:
                os.write(descriptor, candidate)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            descriptor = os.open(path, read_flags)
    try:
        metadata = os.fstat(descriptor)
        if (
            not os.path.isfile(path)
            or metadata.st_uid not in {0, os.geteuid()}
            or metadata.st_mode & 0o077
            or metadata.st_size != 32
        ):
            raise LocalProviderAuthorityError(
                "provider_master_key_unsafe",
                "Ключ шифрования provider-authority настроен небезопасно.",
            )
        key = os.read(descriptor, 33)
    finally:
        os.close(descriptor)
    if len(key) != 32:
        raise LocalProviderAuthorityError(
            "provider_master_key_invalid",
            "Ключ шифрования provider-authority имеет неверный размер.",
        )
    return key


def ensure_local_provider_master_key(settings: Settings) -> bytes:
    _require_development(settings)
    return _read_local_provider_master_key(
        settings,
        create_missing=True,
    )


def load_local_provider_master_key(settings: Settings) -> bytes:
    _require_vault_read(settings)
    return _read_local_provider_master_key(
        settings,
        create_missing=False,
    )


def _write_private_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
    )
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
        os.chmod(path, 0o600)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def _verify_mimo_key(api_key: str) -> None:
    base_url = os.getenv(
        "KOLIBRI_V3_MIMO_BASE_URL",
        "https://token-plan-sgp.xiaomimimo.com/v1",
    ).strip().rstrip("/")
    parsed = urlsplit(base_url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path != "/v1"
        or parsed.query
        or parsed.fragment
    ):
        raise LocalProviderAuthorityError(
            "mimo_base_url_invalid",
            "Адрес MiMo API настроен неверно.",
        )
    try:
        with httpx.Client(
            timeout=httpx.Timeout(15, connect=8),
            follow_redirects=False,
            trust_env=False,
        ) as client:
            response = client.get(
                f"{base_url}/models",
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
            )
    except httpx.HTTPError:
        raise LocalProviderAuthorityError(
            "mimo_connection_failed",
            "Не удалось связаться с MiMo API. Повторите позже.",
        ) from None
    if response.status_code in {401, 403}:
        raise LocalProviderAuthorityError(
            "mimo_api_key_rejected",
            "MiMo отклонил API-ключ. Проверьте ключ Token Plan.",
        )
    if response.status_code != 200:
        raise LocalProviderAuthorityError(
            "mimo_probe_failed",
            f"MiMo API временно недоступен (HTTP {response.status_code}).",
        )


def install_mimo_key(
    settings: Settings,
    api_key: str,
    *,
    tenant_id: str,
) -> dict[str, str]:
    _require_development(settings)
    if api_key != api_key.strip() or not _API_KEY.fullmatch(api_key):
        raise LocalProviderAuthorityError(
            "mimo_api_key_invalid",
            "Ключ MiMo имеет неверный формат.",
        )
    _verify_mimo_key(api_key)

    configured = os.getenv("KOLIBRI_V3_LOCAL_MIMO_AUTH_PATH", "").strip()
    auth_path = (
        Path(configured)
        if configured
        else Path.home() / ".local/share/mimocode/auth.json"
    )
    if not auth_path.is_absolute() or ".." in auth_path.parts:
        raise LocalProviderAuthorityError(
            "mimo_auth_path_invalid",
            "Путь локальной авторизации MiMo настроен неверно.",
        )
    payload = json.dumps(
        {"xiaomi-token-plan-sgp": {"type": "api", "key": api_key}},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    master_key = ensure_local_provider_master_key(settings)
    nonce = os.urandom(12)
    aad = (
        "kolibri-v3-provider-vault-v1\0mimo-code\0" + tenant_id
    ).encode("utf-8", "strict")
    ciphertext = AESGCM(master_key).encrypt(
        nonce,
        api_key.encode("utf-8", "strict"),
        aad,
    )
    database_path = Path(
        settings.database_url.removeprefix("sqlite:///")
    )
    vault_root = (
        database_path.parent
        if database_path.is_absolute()
        else (Path.cwd() / database_path).resolve().parent
    )
    vault_payload = json.dumps(
        {
            "version": 1,
            "algorithm": "AES-256-GCM",
            "provider": "mimo-code",
            "nonce": base64.urlsafe_b64encode(nonce).decode("ascii"),
            "ciphertext": base64.urlsafe_b64encode(ciphertext).decode("ascii"),
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    _write_private_atomic(
        vault_root / "provider-vault" / "mimo-code.v1.enc",
        vault_payload,
    )
    _write_private_atomic(auth_path, payload)

    return {
        "last_verified_at": datetime.now(timezone.utc).isoformat(),
        "evidence_hash": (
            "sha256:" + hashlib.sha256(vault_payload).hexdigest()
        ),
    }


def load_mimo_key(settings: Settings, *, tenant_id: str) -> str:
    """Decrypt the tenant-bound MiMo credential for direct local execution."""

    _require_vault_read(settings)
    database_path = Path(settings.database_url.removeprefix("sqlite:///"))
    vault_root = (
        database_path.parent
        if database_path.is_absolute()
        else (Path.cwd() / database_path).resolve().parent
    )
    vault_path = vault_root / "provider-vault" / "mimo-code.v1.enc"
    try:
        raw = vault_path.read_bytes()
        if len(raw) > 16_384:
            raise ValueError("vault payload is oversized")
        payload = json.loads(raw)
        if (
            payload.get("version") != 1
            or payload.get("algorithm") != "AES-256-GCM"
            or payload.get("provider") != "mimo-code"
        ):
            raise ValueError("vault metadata is invalid")
        nonce = base64.b64decode(
            payload["nonce"].encode("ascii"),
            altchars=b"-_",
            validate=True,
        )
        ciphertext = base64.b64decode(
            payload["ciphertext"].encode("ascii"),
            altchars=b"-_",
            validate=True,
        )
        if len(nonce) != 12 or not 16 <= len(ciphertext) <= 8_208:
            raise ValueError("vault ciphertext is invalid")
        aad = (
            "kolibri-v3-provider-vault-v1\0mimo-code\0" + tenant_id
        ).encode("utf-8", "strict")
        plaintext = AESGCM(
            load_local_provider_master_key(settings)
        ).decrypt(nonce, ciphertext, aad)
        api_key = plaintext.decode("utf-8", "strict")
    except (OSError, ValueError, KeyError, TypeError, UnicodeError, InvalidTag):
        raise LocalProviderAuthorityError(
            "mimo_not_connected",
            "MiMo Code не подключён в личном кабинете.",
        ) from None
    if not _API_KEY.fullmatch(api_key):
        raise LocalProviderAuthorityError(
            "mimo_not_connected",
            "MiMo Code не подключён в личном кабинете.",
        )
    return api_key


def verify_codex_login(settings: Settings) -> dict[str, str]:
    _require_development(settings)
    try:
        result = subprocess.run(
            ["codex", "login", "status"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=10,
            check=False,
            env={
                "HOME": str(Path.home()),
                "PATH": os.getenv("PATH", "/usr/local/bin:/usr/bin:/bin"),
            },
        )
    except (OSError, subprocess.TimeoutExpired):
        raise LocalProviderAuthorityError(
            "codex_login_unavailable",
            "Codex CLI недоступен на локальном runtime.",
        ) from None
    output = result.stdout.strip()
    if result.returncode != 0 or "logged in" not in output.casefold():
        raise LocalProviderAuthorityError(
            "codex_login_required",
            "Сначала выполните вход в Codex CLI на этом компьютере.",
        )
    return {
        "last_verified_at": datetime.now(timezone.utc).isoformat(),
        "evidence_hash": (
            "sha256:"
            + hashlib.sha256(b"codex-login-status:connected").hexdigest()
        ),
    }
