from __future__ import annotations

import os
from pathlib import Path


def kolibri_data_dir() -> Path:
    override = os.getenv("KOLIBRI_DATA_DIR")
    if override:
        path = Path(override).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        return path

    preferred = Path("/opt/kolibri-ai/data")
    try:
        preferred.mkdir(parents=True, exist_ok=True)
        return preferred
    except OSError:
        fallback = Path.home() / ".local" / "share" / "kolibri-ai"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def data_path(*parts: str) -> Path:
    return kolibri_data_dir().joinpath(*parts)
