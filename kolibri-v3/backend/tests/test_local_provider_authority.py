from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from app.config import Settings
from app.local_provider_authority import (
    LocalProviderAuthorityError,
    install_mimo_key,
    load_mimo_key,
)


TENANT_ID = "95c6b48f-b497-4b90-be3f-adb2c923e47d"
MIMO_KEY = "mimo-test-key-" + ("x" * 48)


def _development_settings(database_path: Path) -> Settings:
    return replace(
        Settings.for_testing(database_url=database_path),
        environment="development",
        direct_model_runtime_enabled=True,
    )


def test_production_can_read_preprovisioned_tenant_vault_without_write_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "kolibri-v3.db"
    auth_path = tmp_path / "mimocode" / "auth.json"
    master_key_path = tmp_path / "provider-master-key"
    monkeypatch.setenv(
        "KOLIBRI_V3_PROVIDER_ENCRYPTION_KEY_FILE",
        str(master_key_path),
    )
    monkeypatch.setenv("KOLIBRI_V3_LOCAL_MIMO_AUTH_PATH", str(auth_path))
    monkeypatch.setattr(
        "app.local_provider_authority._verify_mimo_key",
        lambda _key: None,
    )
    development = _development_settings(database_path)
    install_mimo_key(
        development,
        MIMO_KEY,
        tenant_id=TENANT_ID,
    )

    production = replace(
        development,
        environment="production",
        cookie_secure=True,
        allowed_origins=("https://kolibriai.example",),
        local_provider_vault_read_enabled=True,
    )
    assert load_mimo_key(production, tenant_id=TENANT_ID) == MIMO_KEY
    assert master_key_path.stat().st_mode & 0o777 == 0o600
    assert (
        tmp_path / "provider-vault" / "mimo-code.v1.enc"
    ).stat().st_mode & 0o777 == 0o600

    with pytest.raises(LocalProviderAuthorityError) as install_error:
        install_mimo_key(
            production,
            "replacement-" + ("y" * 48),
            tenant_id=TENANT_ID,
        )
    assert install_error.value.code == "local_provider_authority_disabled"


def test_production_vault_read_is_fail_closed_by_default(
    tmp_path: Path,
) -> None:
    settings = replace(
        Settings.for_testing(database_url=tmp_path / "kolibri-v3.db"),
        environment="production",
        cookie_secure=True,
        allowed_origins=("https://kolibriai.example",),
        direct_model_runtime_enabled=True,
        local_provider_vault_read_enabled=False,
    )
    with pytest.raises(LocalProviderAuthorityError) as error:
        load_mimo_key(settings, tenant_id=TENANT_ID)
    assert error.value.code == "local_provider_authority_disabled"


def test_production_vault_read_requires_direct_runtime(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="direct model runtime"):
        replace(
            Settings.for_testing(database_url=tmp_path / "kolibri-v3.db"),
            environment="production",
            cookie_secure=True,
            allowed_origins=("https://kolibriai.example",),
            direct_model_runtime_enabled=False,
            local_provider_vault_read_enabled=True,
        )
