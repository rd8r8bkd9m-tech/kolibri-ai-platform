from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from app.config import Settings
from app.database import database_path


def test_default_database_is_rooted_at_v3_source_not_process_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    foreign_working_directory = tmp_path / "backend"
    foreign_working_directory.mkdir()
    secret_file = tmp_path / "csrf-secret"
    monkeypatch.chdir(foreign_working_directory)
    monkeypatch.delenv("KOLIBRI_V3_DATABASE_URL", raising=False)
    monkeypatch.setenv("KOLIBRI_V3_CSRF_SECRET_FILE", str(secret_file))

    settings = Settings.from_env()
    configured_database = database_path(settings.database_url)

    assert isinstance(configured_database, Path)
    assert configured_database == (
        Path(__file__).resolve().parents[2] / "var" / "kolibri-v3.db"
    )


def _production_base(database_path: Path) -> Settings:
    return replace(
        Settings.for_testing(database_url=database_path),
        environment="production",
        allowed_origins=("https://app.example.test",),
        cookie_secure=True,
    )


def test_production_developer_runtime_is_forbidden_without_workspace(
    tmp_path: Path,
) -> None:
    base = _production_base(tmp_path / "config.db")

    with pytest.raises(
        ValueError,
        match="cannot run in production",
    ):
        replace(
            base,
            direct_model_runtime_enabled=True,
            developer_agent_enabled=True,
            developer_workspace_root=None,
        )


def test_production_developer_runtime_is_forbidden_with_separate_workspace(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "tenant-isolated-workspace"
    workspace.mkdir()

    with pytest.raises(
        ValueError,
        match="cannot run in production",
    ):
        replace(
            _production_base(tmp_path / "safe.db"),
            direct_model_runtime_enabled=True,
            developer_agent_enabled=True,
            developer_workspace_root=workspace,
        )


def test_production_embedded_v3_developer_runtime_is_explicit_and_direct(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "kolibri-v3-workspace"
    workspace.mkdir()

    settings = replace(
        _production_base(tmp_path / "embedded.db"),
        direct_model_runtime_enabled=True,
        developer_agent_enabled=True,
        embedded_developer_runtime_enabled=True,
        developer_workspace_root=workspace,
    )

    assert settings.chat_execution_plane("developer") == "direct"
    assert settings.chat_execution_plane("standard") == "direct"


def test_embedded_v3_developer_runtime_requires_complete_production_capability(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        ValueError,
        match="requires production",
    ):
        replace(
            _production_base(tmp_path / "incomplete.db"),
            embedded_developer_runtime_enabled=True,
        )
