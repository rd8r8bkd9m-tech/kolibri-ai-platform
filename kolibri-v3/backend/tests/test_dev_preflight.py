from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app.config import Settings
from app.database import connect_database, initialize_database, migration_paths
from app.dev_preflight import prepare_development_database
from app.main import create_app
from app.owner_bootstrap import promote_registered_owner


ORIGIN = {"Origin": "http://testserver"}
PASSWORD = "correct-horse-battery-staple"


def _settings(database_path: Path) -> Settings:
    return replace(
        Settings.for_testing(database_url=database_path),
        environment="development",
    )


def test_preflight_migrates_empty_canonical_database(tmp_path: Path) -> None:
    database_path = tmp_path / "canonical.db"
    latest_version = int(migration_paths()[-1].name.split("_", 1)[0])

    assert prepare_development_database(
        _settings(database_path),
        expected_database=database_path,
    ) == (latest_version, 0, 0)


def test_preflight_rejects_an_existing_database_without_platform_owner(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "owner-missing.db"
    settings = _settings(database_path)
    initialize_database(settings.database_url)
    database = connect_database(settings.database_url)
    try:
        database.execute(
            """
            INSERT INTO tenants (id, name, created_at)
            VALUES ('tenant_missing_owner', 'Missing owner', 1)
            """
        )
        database.execute(
            """
            INSERT INTO users (
                id, tenant_id, email_normalized, email, name, role,
                password_hash, created_at, updated_at
            ) VALUES (
                'user_missing_owner', 'tenant_missing_owner',
                'user@example.com', 'user@example.com', 'User', 'user',
                'not-a-real-password-hash', 1, 1
            )
            """
        )
    finally:
        database.close()

    with pytest.raises(RuntimeError, match="exactly one active platform owner"):
        prepare_development_database(
            settings,
            expected_database=database_path,
        )


def test_preflight_accepts_registered_singleton_platform_owner(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "owner-ready.db"
    settings = _settings(database_path)
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/v1/auth/register",
            headers=ORIGIN,
            json={
                "email": "owner@example.com",
                "name": "Owner",
                "password": PASSWORD,
            },
        )
        assert response.status_code == 201
    promote_registered_owner(settings, email="owner@example.com")

    version, user_count, owner_count = prepare_development_database(
        settings,
        expected_database=database_path,
        expected_owner_email="OWNER@example.com",
    )

    assert version == int(migration_paths()[-1].name.split("_", 1)[0])
    assert user_count == 1
    assert owner_count == 1


def test_preflight_rejects_a_different_platform_owner_email(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "wrong-owner.db"
    settings = _settings(database_path)
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/v1/auth/register",
            headers=ORIGIN,
            json={
                "email": "owner@example.com",
                "name": "Owner",
                "password": PASSWORD,
            },
        )
        assert response.status_code == 201
    promote_registered_owner(settings, email="owner@example.com")

    with pytest.raises(
        RuntimeError,
        match="platform owner email does not match",
    ):
        prepare_development_database(
            settings,
            expected_database=database_path,
            expected_owner_email="different@example.com",
        )


def test_preflight_rejects_a_different_database_path(tmp_path: Path) -> None:
    configured = tmp_path / "configured.db"

    with pytest.raises(RuntimeError, match="Wrong V3 database"):
        prepare_development_database(
            _settings(configured),
            expected_database=tmp_path / "other.db",
        )
