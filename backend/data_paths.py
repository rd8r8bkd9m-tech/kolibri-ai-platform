"""Writable Kolibri backend data paths with production-safe defaults."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


PRODUCTION_DATA_DIR = Path("/opt/kolibri-ai/data")


def _prepare(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    probe = path / ".kolibri-write-probe"
    probe.touch(exist_ok=True)
    probe.unlink(missing_ok=True)
    return path


def resolve_data_dir() -> Path:
    configured = os.environ.get("KOLIBRI_DATA_DIR")
    if configured:
        return _prepare(Path(configured).expanduser())
    try:
        return _prepare(PRODUCTION_DATA_DIR)
    except OSError:
        environment = os.environ.get("KOLIBRI_ENV", "development").strip().lower()
        if environment in {"prod", "production"}:
            raise
        uid = getattr(os, "getuid", lambda: 0)()
        return _prepare(Path(tempfile.gettempdir()) / f"kolibri-ai-{uid}" / "data")


DATA_DIR = resolve_data_dir()
DB_PATH = DATA_DIR / "kolibri.db"
TTS_DIR = DATA_DIR / "tts"
CACHE_DIR = DATA_DIR / "cache"

for directory in (TTS_DIR, CACHE_DIR):
    directory.mkdir(parents=True, exist_ok=True)
