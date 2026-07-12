"""Verified, session-scoped image artifacts for the public Kolibri Shell.

An image artifact is created only from bytes whose container signature is
validated.  The bytes are stored content-addressed, while the public locator is
bound to one short-lived browser session and response.  Provider prose, a file
extension, or a worker path can never create an artifact record.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from data_paths import DATA_DIR, DB_PATH
from sqlite_lifecycle import closing_sqlite_transaction


IMAGE_ARTIFACT_SCHEMA = "kolibri.public-image-artifact.v1"
IMAGE_ARTIFACT_BINDING_SCHEMA = "kolibri.public-image-artifact-binding.v1"
MAX_IMAGE_BYTES = 8 * 1024 * 1024
_SHA256 = re.compile(r"^[a-f0-9]{64}$")


class ImageArtifactError(RuntimeError):
    pass


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ImageArtifactError("image_artifact_binding_not_canonical") from exc


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha_value(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def validated_image_media_type(content: bytes) -> str:
    """Return the media type only for a complete PNG/JPEG/WebP container."""

    if not isinstance(content, bytes) or not content:
        raise ImageArtifactError("image_content_empty")
    if len(content) > MAX_IMAGE_BYTES:
        raise ImageArtifactError("image_content_too_large")
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        # A PNG must contain IHDR first and a terminal IEND chunk.  This is a
        # bounded container check, not merely an eight-byte magic comparison.
        if len(content) < 33 or content[12:16] != b"IHDR" or content[-8:-4] != b"IEND":
            raise ImageArtifactError("image_png_container_invalid")
        return "image/png"
    if content.startswith(b"\xff\xd8"):
        if len(content) < 4 or not content.endswith(b"\xff\xd9"):
            raise ImageArtifactError("image_jpeg_container_invalid")
        return "image/jpeg"
    if len(content) >= 16 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        declared_size = int.from_bytes(content[4:8], "little") + 8
        if declared_size != len(content) or content[12:16] not in {b"VP8 ", b"VP8L", b"VP8X"}:
            raise ImageArtifactError("image_webp_container_invalid")
        return "image/webp"
    raise ImageArtifactError("image_media_type_unsupported")


def image_extension(media_type: str) -> str:
    return {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}.get(
        media_type,
        "bin",
    )


class PublicImageArtifactStore:
    def __init__(self, db_path: str | Path, artifact_root: str | Path):
        self.db_path = str(db_path)
        self.artifact_root = Path(artifact_root).expanduser().resolve()
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_schema()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_schema(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._lock, closing_sqlite_transaction(self.connect) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS public_image_artifacts (
                    artifact_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    response_id TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    reference_sha256 TEXT NOT NULL,
                    binding_sha256 TEXT NOT NULL,
                    factory_binding_sha256 TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    storage_path TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    UNIQUE(session_id, response_id, content_sha256)
                );
                CREATE INDEX IF NOT EXISTS idx_public_image_artifacts_session
                    ON public_image_artifacts(session_id, created_at);
                """
            )

    def _cleanup(self, connection: sqlite3.Connection, now: float) -> None:
        expired = connection.execute(
            "SELECT DISTINCT storage_path FROM public_image_artifacts WHERE expires_at <= ?",
            (now,),
        ).fetchall()
        connection.execute("DELETE FROM public_image_artifacts WHERE expires_at <= ?", (now,))
        for row in expired:
            storage_path = str(row["storage_path"])
            remaining = connection.execute(
                "SELECT 1 FROM public_image_artifacts WHERE storage_path = ? LIMIT 1",
                (storage_path,),
            ).fetchone()
            if remaining is None:
                path = Path(storage_path).resolve()
                if path.is_relative_to(self.artifact_root):
                    path.unlink(missing_ok=True)

    @staticmethod
    def _public(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        get = row.__getitem__
        extension = image_extension(str(get("media_type")))
        return {
            "id": get("artifact_id"),
            "schema_version": IMAGE_ARTIFACT_SCHEMA,
            "kind": "image",
            "name": f"Изображение Kolibri.{extension}",
            "locator": f"/v1/public/artifacts/{get('artifact_id')}/content",
            "media_type": get("media_type"),
            "reference_sha256": get("reference_sha256"),
            "content_sha256": get("content_sha256"),
            "size_bytes": int(get("size_bytes")),
            "deliverable_type": "image",
            "evidence_binding_sha256": get("binding_sha256"),
            "status": "materialized",
            "immutable": True,
        }

    def persist(
        self,
        *,
        session: dict[str, Any],
        response_id: str,
        content: bytes,
        factory_binding_sha256: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        media_type = validated_image_media_type(content)
        if not _SHA256.fullmatch(str(factory_binding_sha256 or "").lower()):
            raise ImageArtifactError("image_factory_binding_invalid")
        content_sha = _sha_bytes(content)
        size_bytes = len(content)
        binding_payload = {
            "schema_version": IMAGE_ARTIFACT_BINDING_SCHEMA,
            "session_sha256": _sha_value(str(session["id"])),
            "project_id": str(session["project_id"]),
            "response_id": str(response_id),
            "content_sha256": content_sha,
            "media_type": media_type,
            "size_bytes": size_bytes,
            "factory_binding_sha256": str(factory_binding_sha256).lower(),
        }
        binding_sha = _sha_value(binding_payload)
        artifact_id = f"artifact_image_{binding_sha[:32]}"
        reference_sha = _sha_value({
            "schema_version": IMAGE_ARTIFACT_SCHEMA,
            "artifact_id": artifact_id,
            "content_sha256": content_sha,
            "binding_sha256": binding_sha,
        })
        extension = image_extension(media_type)
        directory = self.artifact_root / content_sha[:2]
        storage_path = directory / f"{content_sha}.{extension}"
        now = time.time()
        expires_at = float(session["expires_at"])
        with self._lock, closing_sqlite_transaction(self.connect) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._cleanup(connection, now)
            existing = connection.execute(
                """SELECT * FROM public_image_artifacts
                   WHERE session_id = ? AND response_id = ? AND content_sha256 = ?""",
                (session["id"], response_id, content_sha),
            ).fetchone()
            if existing is not None:
                path = Path(str(existing["storage_path"])).resolve()
                if not path.is_relative_to(self.artifact_root) or not path.is_file():
                    raise ImageArtifactError("image_artifact_storage_missing")
                stored = path.read_bytes()
                if (
                    validated_image_media_type(stored) != existing["media_type"]
                    or len(stored) != int(existing["size_bytes"])
                    or _sha_bytes(stored) != existing["content_sha256"]
                ):
                    raise ImageArtifactError("image_artifact_content_mismatch")
                artifact = self._public(existing)
                return artifact, self._materialization_proof(existing)
            directory.mkdir(parents=True, exist_ok=True)
            temporary = directory / f".{content_sha}.{os.getpid()}.{threading.get_ident()}.tmp"
            temporary.write_bytes(content)
            if _sha_bytes(temporary.read_bytes()) != content_sha:
                temporary.unlink(missing_ok=True)
                raise ImageArtifactError("image_content_write_verification_failed")
            temporary.replace(storage_path)
            connection.execute(
                """INSERT INTO public_image_artifacts
                   (artifact_id, session_id, project_id, response_id, media_type,
                    content_sha256, reference_sha256, binding_sha256,
                    factory_binding_sha256, size_bytes, storage_path, created_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    artifact_id,
                    session["id"],
                    session["project_id"],
                    response_id,
                    media_type,
                    content_sha,
                    reference_sha,
                    binding_sha,
                    str(factory_binding_sha256).lower(),
                    size_bytes,
                    str(storage_path),
                    now,
                    expires_at,
                ),
            )
            row = connection.execute(
                "SELECT * FROM public_image_artifacts WHERE artifact_id = ?",
                (artifact_id,),
            ).fetchone()
        if row is None:
            raise ImageArtifactError("image_artifact_persistence_failed")
        return self._public(row), self._materialization_proof(row)

    @staticmethod
    def _materialization_proof(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        get = row.__getitem__
        return {
            "type": "artifact_materialization",
            "verdict": "passed",
            "deliverable_type": "image",
            "reference_sha256": get("reference_sha256"),
            "content_sha256": get("content_sha256"),
            "size_bytes": int(get("size_bytes")),
            "binding_sha256": get("binding_sha256"),
        }

    def content(
        self,
        session_id: str,
        artifact_id: str,
    ) -> tuple[dict[str, Any], bytes] | None:
        now = time.time()
        with self._lock, closing_sqlite_transaction(self.connect) as connection:
            self._cleanup(connection, now)
            row = connection.execute(
                """SELECT * FROM public_image_artifacts
                   WHERE artifact_id = ? AND session_id = ? AND expires_at > ?""",
                (artifact_id, session_id, now),
            ).fetchone()
        if row is None:
            return None
        path = Path(str(row["storage_path"])).resolve()
        if not path.is_relative_to(self.artifact_root) or not path.is_file():
            raise ImageArtifactError("image_artifact_storage_missing")
        content = path.read_bytes()
        media_type = validated_image_media_type(content)
        if (
            media_type != row["media_type"]
            or len(content) != int(row["size_bytes"])
            or _sha_bytes(content) != row["content_sha256"]
        ):
            raise ImageArtifactError("image_artifact_content_mismatch")
        return self._public(row), content


_STORE = PublicImageArtifactStore(
    DB_PATH,
    os.environ.get(
        "KOLIBRI_PUBLIC_IMAGE_ARTIFACT_ROOT",
        str(DATA_DIR / "public-image-artifacts"),
    ),
)


def configure_public_image_artifact_store(
    db_path: str | Path,
    artifact_root: str | Path,
) -> PublicImageArtifactStore:
    global _STORE
    _STORE = PublicImageArtifactStore(db_path, artifact_root)
    return _STORE


def get_public_image_artifact_store() -> PublicImageArtifactStore:
    return _STORE
