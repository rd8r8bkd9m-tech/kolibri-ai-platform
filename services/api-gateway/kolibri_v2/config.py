from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_ALLOWED_API_KEY_ROLES = {"client", "developer", "operator", "owner"}


def _api_key_seeds() -> tuple[tuple[str, str, str], ...]:
    """Load bootstrap API keys from an env JSON object and/or a JSON file.

    Accepted shape::

        {
          "sk-kolibri-example": "developer",
          "sk-kolibri-owner": {"role": "owner", "name": "release"}
        }

    Raw bootstrap keys are only used at startup; the store persists SHA-256 hashes.
    """

    merged: dict[str, Any] = {}
    file_name = os.environ.get("KOLIBRI_API_KEYS_FILE")
    if file_name:
        path = Path(file_name).expanduser().resolve()
        if not path.is_file():
            raise RuntimeError(f"KOLIBRI_API_KEYS_FILE does not exist: {path}")
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise RuntimeError("KOLIBRI_API_KEYS_FILE must contain a JSON object")
        merged.update(loaded)
    inline = os.environ.get("KOLIBRI_API_KEYS_JSON")
    if inline:
        loaded = json.loads(inline)
        if not isinstance(loaded, dict):
            raise RuntimeError("KOLIBRI_API_KEYS_JSON must be a JSON object")
        merged.update(loaded)

    seeds: list[tuple[str, str, str]] = []
    for raw_key, spec in merged.items():
        if not isinstance(raw_key, str) or not raw_key.startswith("sk-kolibri-") or len(raw_key) < 24:
            raise RuntimeError("Every bootstrap API key must start with 'sk-kolibri-' and be at least 24 characters")
        if isinstance(spec, str):
            role, name = spec, "bootstrap"
        elif isinstance(spec, dict):
            role = str(spec.get("role", "developer"))
            name = str(spec.get("name", "bootstrap"))
        else:
            raise RuntimeError("API key specification must be a role string or object")
        if role not in _ALLOWED_API_KEY_ROLES:
            raise RuntimeError(f"Unsupported API key role: {role}")
        seeds.append((raw_key, role, name[:120] or "bootstrap"))
    return tuple(seeds)


@dataclass(frozen=True)
class Settings:
    env: str
    data_dir: Path
    db_path: Path
    artifact_dir: Path
    session_cookie: str
    session_secret: str
    allowed_origins: tuple[str, ...]
    public_model: str
    openai_base_url: str | None
    openai_api_key: str | None
    openai_project: str | None
    openai_organization: str | None
    node_join_token: str | None
    owner_access_token: str | None
    operator_access_token: str | None
    developer_access_token: str | None
    expose_session_token: bool
    bootstrap_api_keys: tuple[tuple[str, str, str], ...]

    @classmethod
    def load(cls) -> "Settings":
        root = Path(os.environ.get("KOLIBRI_DATA_DIR", "data")).expanduser().resolve()
        origins = tuple(
            origin.strip()
            for origin in os.environ.get(
                "KOLIBRI_ALLOWED_ORIGINS",
                "http://127.0.0.1:5173,http://localhost:5173",
            ).split(",")
            if origin.strip()
        )
        db_path = Path(os.environ.get("KOLIBRI_DB_PATH", root / "kolibri.db")).expanduser().resolve()
        artifact_dir = Path(os.environ.get("KOLIBRI_ARTIFACT_DIR", root / "artifacts")).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        env = os.environ.get("KOLIBRI_ENV", "development")
        return cls(
            env=env,
            data_dir=root,
            db_path=db_path,
            artifact_dir=artifact_dir,
            session_cookie=os.environ.get("KOLIBRI_SESSION_COOKIE", "kolibri_session"),
            session_secret=os.environ.get("KOLIBRI_SESSION_SECRET", "dev-only-change-me"),
            allowed_origins=origins,
            public_model="kolibri",
            openai_base_url=os.environ.get("OPENAI_BASE_URL"),
            openai_api_key=os.environ.get("OPENAI_API_KEY"),
            openai_project=os.environ.get("OPENAI_PROJECT"),
            openai_organization=os.environ.get("OPENAI_ORGANIZATION"),
            node_join_token=os.environ.get("KOLIBRI_NODE_JOIN_TOKEN"),
            owner_access_token=os.environ.get("KOLIBRI_OWNER_ACCESS_TOKEN"),
            operator_access_token=os.environ.get("KOLIBRI_OPERATOR_ACCESS_TOKEN"),
            developer_access_token=os.environ.get("KOLIBRI_DEVELOPER_ACCESS_TOKEN"),
            expose_session_token=os.environ.get(
                "KOLIBRI_EXPOSE_SESSION_TOKEN", "1" if env != "production" else "0"
            ) == "1",
            bootstrap_api_keys=_api_key_seeds(),
        )
