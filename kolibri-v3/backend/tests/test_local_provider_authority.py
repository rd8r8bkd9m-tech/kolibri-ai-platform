from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from app.config import Settings
from app.local_provider_authority import (
    LocalProviderAuthorityError,
    ensure_local_provider_master_key,
    load_mimo_key,
)


def _production_settings(database_path: Path, *, vault_read: bool) -> Settings:
    return replace(
        Settings.for_testing(database_url=database_path),
        environment="production",
        allowed_origins=("https://app.example.test",),
        cookie_secure=True,
        local_provider_vault_read_enabled=vault_read,
    )


def test_production_vault_read_is_explicit_and_read_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    master_key_path = tmp_path / "provider-master-key"
    master_key_path.write_bytes(b"k" * 32)
    master_key_path.chmod(0o600)
    monkeypatch.setenv(
        "KOLIBRI_V3_PROVIDER_ENCRYPTION_KEY_FILE",
        str(master_key_path),
    )

    disabled = _production_settings(tmp_path / "disabled.db", vault_read=False)
    with pytest.raises(LocalProviderAuthorityError) as error:
        ensure_local_provider_master_key(disabled)
    assert error.value.code == "local_provider_authority_disabled"

    enabled = _production_settings(tmp_path / "enabled.db", vault_read=True)
    assert ensure_local_provider_master_key(enabled) == b"k" * 32
    assert not (tmp_path / "enabled.db").exists()


def test_production_vault_read_fails_closed_when_master_key_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "KOLIBRI_V3_PROVIDER_ENCRYPTION_KEY_FILE",
        str(tmp_path / "missing-master-key"),
    )
    settings = _production_settings(tmp_path / "missing.db", vault_read=True)

    with pytest.raises(LocalProviderAuthorityError) as error:
        ensure_local_provider_master_key(settings)
    assert error.value.code == "provider_master_key_unavailable"


def test_mimo_key_read_uses_the_same_explicit_gate(
    tmp_path: Path,
) -> None:
    settings = _production_settings(tmp_path / "mimo.db", vault_read=False)

    with pytest.raises(LocalProviderAuthorityError) as error:
        load_mimo_key(settings, tenant_id="tenant-test")
    assert error.value.code == "local_provider_authority_disabled"
