from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Callable

from .config import Settings
from .store import Store


class ArtifactService:
    def __init__(self, settings: Settings, store: Store):
        self.settings = settings
        self.store = store

    def materialize(
        self,
        *,
        session_id: str,
        name: str,
        mime_type: str,
        data: bytes,
        project_id: str | None = None,
        estimate_id: str | None = None,
        task_id: str | None = None,
        revision: int | None = None,
    ) -> dict:
        digest = hashlib.sha256(data).hexdigest()
        suffix = Path(name).suffix or ".bin"
        target_dir = self.settings.artifact_dir / digest[:2]
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{digest}{suffix}"
        if not target.exists():
            target.write_bytes(data)
        return self.store.add_artifact(
            session_id=session_id,
            project_id=project_id,
            estimate_id=estimate_id,
            task_id=task_id,
            revision=revision,
            name=name,
            mime_type=mime_type,
            size=len(data),
            sha256=digest,
            storage_path=str(target),
        )
