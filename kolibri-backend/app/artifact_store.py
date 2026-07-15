"""Persistent, content-addressed storage for materialized Kolibri artifacts.

An artifact is not a filename or a provider claim.  It is a bounded byte
sequence with a verified media type, size and SHA-256 digest, plus an immutable
revision manifest.  The mutable ``head.json`` pointer is updated only after the
blob and revision manifest have been durably written.

The filesystem implementation is intentionally behind :class:`ArtifactStore`.
It gives the current single-node backend real persistence while keeping the
public contract suitable for a future S3/CAS adapter.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
import hashlib
import hmac
import json
import mimetypes
import os
from pathlib import Path
import re
import tempfile
import threading
from typing import Any, Iterator
from urllib.parse import quote
import uuid
import zipfile

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from app.browser_session import ProjectPrincipal
from app.public_scope import resolve_optional_public_scope

try:  # Linux and macOS production/development runtimes.
    import fcntl
except ImportError:  # pragma: no cover - defensive fallback for Windows wrappers.
    fcntl = None


ARTIFACT_SCHEMA_VERSION = "kolibri.artifact.v1"
DEFAULT_MAX_ARTIFACT_BYTES = 100 * 1024 * 1024
MAX_METADATA_BYTES = 64 * 1024
MAX_MANIFEST_BYTES = 128 * 1024
_UUID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MIME = re.compile(r"^[a-z0-9][a-z0-9!#$&^_.+-]{0,126}/[a-z0-9][a-z0-9!#$&^_.+-]{0,126}$")
_ARTIFACT_TYPE = re.compile(r"^[a-z][a-z0-9_.-]{0,39}$")
_ROUTE_PREFIX = re.compile(r"^/api/v1/artifacts(?:/[a-z][a-z0-9_-]{0,39})?$")
_local_lock = threading.RLock()


class ArtifactStoreError(RuntimeError):
    """Base class for artifact persistence failures."""


class ArtifactNotFound(ArtifactStoreError):
    """The requested artifact or revision does not exist."""


class ArtifactConflict(ArtifactStoreError):
    """A compare-and-swap revision precondition failed."""


class ArtifactValidationError(ArtifactStoreError):
    """Artifact bytes or metadata do not meet the storage contract."""


class ArtifactIntegrityError(ArtifactStoreError):
    """Persisted bytes no longer match their immutable manifest."""


@dataclass(frozen=True)
class StoredArtifact:
    manifest: dict[str, Any]
    content: bytes


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_uuid(value: str) -> str:
    candidate = str(value or "").lower()
    if not _UUID.fullmatch(candidate):
        raise ArtifactValidationError("artifact_id_invalid")
    try:
        normalized = str(uuid.UUID(candidate))
    except ValueError as exc:  # pragma: no cover - regex already narrows the value.
        raise ArtifactValidationError("artifact_id_invalid") from exc
    if normalized != candidate:
        raise ArtifactValidationError("artifact_id_invalid")
    return normalized


def _normalize_filename(value: str | None, *, mime_type: str) -> str:
    filename = str(value or "artifact").strip()
    if (
        not filename
        or filename in {".", ".."}
        or filename != Path(filename).name
        or "/" in filename
        or "\\" in filename
        or "\x00" in filename
        or "\r" in filename
        or "\n" in filename
        or len(filename.encode("utf-8")) > 240
    ):
        raise ArtifactValidationError("artifact_filename_invalid")
    if filename == "artifact":
        extension = mimetypes.guess_extension(mime_type, strict=False) or ""
        filename = f"artifact{extension}"
    return filename


def _json_metadata(value: dict[str, Any] | None) -> tuple[dict[str, Any], bytes]:
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise ArtifactValidationError("artifact_metadata_invalid")
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ArtifactValidationError("artifact_metadata_invalid") from exc
    if len(encoded) > MAX_METADATA_BYTES:
        raise ArtifactValidationError("artifact_metadata_too_large")
    # Round-trip to detach the persisted value from caller-owned mutable data.
    return json.loads(encoded), encoded


def _zip_mime(data: bytes) -> str | None:
    if not data.startswith(b"PK\x03\x04"):
        return None
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            names = set(archive.namelist())
    except (OSError, zipfile.BadZipFile):
        raise ArtifactValidationError("artifact_zip_invalid")
    if "[Content_Types].xml" in names:
        if any(name.startswith("word/") for name in names):
            return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if any(name.startswith("xl/") for name in names):
            return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if any(name.startswith("ppt/") for name in names):
            return "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    return "application/zip"


def detect_mime_type(data: bytes) -> str | None:
    """Detect formats for which Kolibri makes a strong MIME assertion."""

    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8") and data.endswith(b"\xff\xd9"):
        return "image/jpeg"
    if data.startswith(b"RIFF") and len(data) >= 12 and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data.startswith(b"%PDF-"):
        if b"%%EOF" not in data[-1024:]:
            raise ArtifactValidationError("artifact_pdf_invalid")
        return "application/pdf"
    zip_mime = _zip_mime(data)
    if zip_mime:
        return zip_mime
    return None


def _validated_mime(data: bytes, requested: str | None) -> str:
    requested = str(requested or "").strip().lower()
    if requested and not _MIME.fullmatch(requested):
        raise ArtifactValidationError("artifact_mime_invalid")
    detected = detect_mime_type(data)
    if requested:
        if detected is not None and detected != requested:
            raise ArtifactValidationError("artifact_mime_mismatch")
        if requested.startswith("image/") and detected != requested:
            raise ArtifactValidationError("artifact_image_mime_unverified")
        if requested == "application/pdf" and detected != requested:
            raise ArtifactValidationError("artifact_pdf_mime_unverified")
        if requested in {
            "application/zip",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        } and detected != requested:
            raise ArtifactValidationError("artifact_archive_mime_unverified")
        if requested == "application/json":
            try:
                json.loads(data)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ArtifactValidationError("artifact_json_invalid") from exc
        if requested.startswith("text/"):
            try:
                data.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ArtifactValidationError("artifact_text_not_utf8") from exc
        return requested
    return detected or "application/octet-stream"


def _safe_root_path(root: Path, *parts: str) -> Path:
    root = root.resolve()
    candidate = root.joinpath(*parts).resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ArtifactValidationError("artifact_path_outside_root") from exc
    return candidate


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _atomic_write(path: Path, data: bytes, *, mode: int = 0o640) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            temporary.write(data)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.chmod(temporary_name, mode)
        os.replace(temporary_name, path)
        temporary_name = None
        _fsync_directory(path.parent)
    finally:
        if temporary_name is not None:
            try:
                Path(temporary_name).unlink()
            except FileNotFoundError:
                pass


class ArtifactStore:
    """Filesystem-backed immutable revision manifests and SHA-256 blobs."""

    def __init__(self, root: str | Path | None = None, *, max_bytes: int | None = None):
        configured = root if root is not None else os.getenv("KOLIBRI_ARTIFACT_DIR", "./data/artifacts")
        self.root = Path(configured).expanduser().resolve()
        try:
            configured_limit = max_bytes if max_bytes is not None else int(
                os.getenv("KOLIBRI_MAX_ARTIFACT_BYTES", str(DEFAULT_MAX_ARTIFACT_BYTES))
            )
        except (TypeError, ValueError) as exc:
            raise ArtifactValidationError("artifact_size_limit_invalid") from exc
        if configured_limit <= 0:
            raise ArtifactValidationError("artifact_size_limit_invalid")
        self.max_bytes = configured_limit
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, *parts: str) -> Path:
        return _safe_root_path(self.root, *parts)

    def _artifact_dir(self, artifact_id: str) -> Path:
        return self._path("artifacts", artifact_id[:2], artifact_id)

    def _head_path(self, artifact_id: str) -> Path:
        return self._path("artifacts", artifact_id[:2], artifact_id, "head.json")

    def _revision_path(self, artifact_id: str, revision: int) -> Path:
        if revision < 1:
            raise ArtifactValidationError("artifact_revision_invalid")
        return self._path(
            "artifacts",
            artifact_id[:2],
            artifact_id,
            "revisions",
            f"{revision:08d}.json",
        )

    def _blob_path(self, digest: str) -> Path:
        if not _SHA256.fullmatch(digest):
            raise ArtifactValidationError("artifact_digest_invalid")
        return self._path("blobs", "sha256", digest[:2], digest)

    @contextmanager
    def _lock(self, artifact_id: str) -> Iterator[None]:
        lock_path = self._path("locks", f"{artifact_id}.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        if fcntl is None:  # pragma: no cover - Windows wrapper fallback.
            with _local_lock:
                yield
            return
        descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o640)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    @staticmethod
    def _route_prefix(value: str | None) -> str:
        prefix = str(value or "/api/v1/artifacts").rstrip("/")
        if not _ROUTE_PREFIX.fullmatch(prefix) or ".." in prefix:
            raise ArtifactValidationError("artifact_route_prefix_invalid")
        return prefix

    def _read_json(self, path: Path) -> dict[str, Any]:
        try:
            if path.stat().st_size > MAX_MANIFEST_BYTES:
                raise ArtifactIntegrityError("artifact_manifest_too_large")
            raw = path.read_bytes()
        except FileNotFoundError as exc:
            raise ArtifactNotFound("artifact_not_found") from exc
        except OSError as exc:
            raise ArtifactIntegrityError("artifact_manifest_unreadable") from exc
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ArtifactIntegrityError("artifact_manifest_invalid") from exc
        if not isinstance(value, dict):
            raise ArtifactIntegrityError("artifact_manifest_invalid")
        return value

    def _read_manifest(self, artifact_id: str, revision: int | None = None) -> dict[str, Any]:
        artifact_id = _normalize_uuid(artifact_id)
        if revision is None:
            head = self._read_json(self._head_path(artifact_id))
            if (
                head.get("schema_version") != ARTIFACT_SCHEMA_VERSION
                or head.get("id") != artifact_id
                or not isinstance(head.get("revision"), int)
            ):
                raise ArtifactIntegrityError("artifact_head_invalid")
            revision = head["revision"]
        manifest = self._read_json(self._revision_path(artifact_id, revision))
        if (
            manifest.get("schema_version") != ARTIFACT_SCHEMA_VERSION
            or manifest.get("id") != artifact_id
            or manifest.get("revision") != revision
            or not _SHA256.fullmatch(str(manifest.get("sha256") or ""))
        ):
            raise ArtifactIntegrityError("artifact_manifest_invalid")
        return manifest

    @staticmethod
    def _public_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in manifest.items() if not key.startswith("_")}

    def put_bytes(
        self,
        content: bytes | bytearray | memoryview,
        *,
        artifact_type: str,
        mime_type: str | None = None,
        filename: str | None = None,
        title: str | None = None,
        metadata: dict[str, Any] | None = None,
        artifact_id: str | None = None,
        expected_revision: int | None = None,
        route_prefix: str | None = None,
    ) -> dict[str, Any]:
        data = bytes(content)
        if not data:
            raise ArtifactValidationError("artifact_bytes_empty")
        if len(data) > self.max_bytes:
            raise ArtifactValidationError("artifact_bytes_exceed_limit")
        artifact_type = str(artifact_type or "").strip().lower()
        if not _ARTIFACT_TYPE.fullmatch(artifact_type):
            raise ArtifactValidationError("artifact_type_invalid")
        selected_mime = _validated_mime(data, mime_type)
        selected_filename = _normalize_filename(filename, mime_type=selected_mime)
        selected_title = " ".join(str(title or selected_filename).split())
        if not selected_title or len(selected_title) > 240:
            raise ArtifactValidationError("artifact_title_invalid")
        metadata_value, _ = _json_metadata(metadata)
        prefix = self._route_prefix(route_prefix)
        identifier = _normalize_uuid(artifact_id) if artifact_id else str(uuid.uuid4())
        digest = hashlib.sha256(data).hexdigest()

        with self._lock(identifier):
            try:
                current = self._read_manifest(identifier)
            except ArtifactNotFound:
                current = None
            if current is None:
                if expected_revision not in (None, 0):
                    raise ArtifactConflict("artifact_revision_conflict")
                revision = 1
                created_at = _utc_now()
            else:
                current_revision = int(current["revision"])
                if expected_revision is None or expected_revision != current_revision:
                    raise ArtifactConflict("artifact_revision_conflict")
                if current.get("type") != artifact_type:
                    raise ArtifactValidationError("artifact_type_immutable")
                current_prefix = str(current.get("url") or "").rsplit("/", 1)[0]
                if current_prefix != prefix:
                    raise ArtifactValidationError("artifact_route_immutable")
                revision = current_revision + 1
                created_at = str(current["created_at"])
            updated_at = _utc_now()
            url = f"{prefix}/{identifier}"
            canonical_url = f"/api/v1/artifacts/{identifier}"
            manifest: dict[str, Any] = {
                "schema_version": ARTIFACT_SCHEMA_VERSION,
                "id": identifier,
                "type": artifact_type,
                "revision": revision,
                "title": selected_title,
                "filename": selected_filename,
                "mime_type": selected_mime,
                "size_bytes": len(data),
                "sha256": digest,
                "created_at": created_at,
                "updated_at": updated_at,
                "metadata": metadata_value,
                "url": url,
                "download_url": f"{url}?download=true",
                "revision_url": f"{canonical_url}?revision={revision}",
                "revision_download_url": (
                    f"{canonical_url}?revision={revision}&download=true"
                ),
                "reopen_url": f"{canonical_url}/reopen",
                "history_url": f"{canonical_url}/history",
                "_blob": {"algorithm": "sha256", "digest": digest},
            }
            encoded_manifest = json.dumps(
                manifest,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
            blob_path = self._blob_path(digest)
            if blob_path.exists():
                try:
                    existing = blob_path.read_bytes()
                except OSError as exc:
                    raise ArtifactIntegrityError("artifact_blob_unreadable") from exc
                if len(existing) != len(data) or hashlib.sha256(existing).hexdigest() != digest:
                    raise ArtifactIntegrityError("artifact_blob_collision_or_corruption")
            else:
                _atomic_write(blob_path, data)
            _atomic_write(self._revision_path(identifier, revision), encoded_manifest)
            head = json.dumps(
                {"schema_version": ARTIFACT_SCHEMA_VERSION, "id": identifier, "revision": revision},
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            _atomic_write(self._head_path(identifier), head)
            return self._public_manifest(manifest)

    def get(self, artifact_id: str, *, revision: int | None = None) -> dict[str, Any]:
        return self._public_manifest(self._read_manifest(artifact_id, revision))

    def open(self, artifact_id: str, *, revision: int | None = None) -> StoredArtifact:
        manifest = self._read_manifest(artifact_id, revision)
        digest = str(manifest["sha256"])
        try:
            content = self._blob_path(digest).read_bytes()
        except (FileNotFoundError, OSError) as exc:
            raise ArtifactIntegrityError("artifact_blob_missing") from exc
        if len(content) != manifest.get("size_bytes") or hashlib.sha256(content).hexdigest() != digest:
            raise ArtifactIntegrityError("artifact_blob_integrity_failed")
        try:
            actual_mime = _validated_mime(content, str(manifest.get("mime_type") or ""))
        except ArtifactValidationError as exc:
            raise ArtifactIntegrityError("artifact_mime_integrity_failed") from exc
        if actual_mime != manifest.get("mime_type"):
            raise ArtifactIntegrityError("artifact_mime_integrity_failed")
        return StoredArtifact(self._public_manifest(manifest), content)

    def history(self, artifact_id: str) -> list[dict[str, Any]]:
        artifact_id = _normalize_uuid(artifact_id)
        head = self._read_manifest(artifact_id)
        # Only revisions committed by the atomic head pointer are visible.
        return [
            self.open(artifact_id, revision=revision).manifest
            for revision in range(1, int(head["revision"]) + 1)
        ]

    def list(
        self,
        *,
        artifact_type: str | None = None,
        metadata: dict[str, Any] | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List committed heads for internal library/indexing services.

        This deliberately has no unauthenticated HTTP route: a project-aware
        service must apply ownership/tenant policy before exposing a library.
        """

        if artifact_type is not None:
            artifact_type = str(artifact_type).strip().lower()
            if not _ARTIFACT_TYPE.fullmatch(artifact_type):
                raise ArtifactValidationError("artifact_type_invalid")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 1_000:
            raise ArtifactValidationError("artifact_list_limit_invalid")
        metadata_filter, _ = _json_metadata(metadata)
        artifacts_root = self._path("artifacts")
        if not artifacts_root.exists():
            return []
        items: list[dict[str, Any]] = []
        for head_path in artifacts_root.glob("*/*/head.json"):
            identifier = head_path.parent.name
            try:
                artifact = self.get(identifier)
            except ArtifactValidationError as exc:
                raise ArtifactIntegrityError("artifact_index_invalid") from exc
            stored_metadata = artifact.get("metadata")
            metadata_matches = isinstance(stored_metadata, dict) and all(
                stored_metadata.get(key) == value
                for key, value in metadata_filter.items()
            )
            if (
                (artifact_type is None or artifact.get("type") == artifact_type)
                and metadata_matches
            ):
                items.append(artifact)
        items.sort(
            key=lambda item: (str(item.get("updated_at") or ""), str(item.get("id") or "")),
            reverse=True,
        )
        return items[:limit]

    def reopen(self, artifact_id: str, *, revision: int | None = None) -> dict[str, Any]:
        artifact = self.open(artifact_id, revision=revision).manifest
        selected_revision = int(artifact["revision"])
        separator = "&" if "?" in artifact["url"] else "?"
        return {
            "artifact": artifact,
            "revision": selected_revision,
            "content_url": artifact.get("revision_url")
            or f"{artifact['url']}{separator}revision={selected_revision}",
            "download_url": artifact.get("revision_download_url")
            or f"{artifact['url']}{separator}revision={selected_revision}&download=true",
            "integrity": {"algorithm": "sha256", "digest": artifact["sha256"]},
        }


def get_artifact_store() -> ArtifactStore:
    """Build a request-local store so tests and deployments can change the root."""

    return ArtifactStore()


router = APIRouter(tags=["artifacts"])


_PUBLIC_IMAGE_METADATA_FIELDS = {
    "height",
    "prompt",
    "source_artifact_id",
    "width",
}


def _public_http_artifact_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    """Detach a manifest and hide image execution provenance from browsers.

    Internal CAS callers continue to receive the full immutable manifest. The
    bounded projection is applied only by the authenticated public reopen and
    history routes. Non-image artifact contracts are intentionally unchanged.
    """

    public = json.loads(json.dumps(manifest, ensure_ascii=False))
    if public.get("type") != "image":
        return public
    metadata = public.get("metadata")
    public["metadata"] = (
        {
            key: value
            for key, value in metadata.items()
            if key in _PUBLIC_IMAGE_METADATA_FIELDS
        }
        if isinstance(metadata, dict)
        else {}
    )
    for key in ("provider", "provider_route", "selected_route_id", "topology"):
        public.pop(key, None)
    if "model" in public:
        public["model"] = "kolibri"
    return public


def _assert_http_artifact_access(
    artifact: dict[str, Any],
    principal: ProjectPrincipal | None,
) -> None:
    """Hide an artifact unless it has a matching opaque owner binding."""

    _assert_artifact_scope(
        artifact,
        principal.scope_id if principal is not None else None,
    )


def _assert_artifact_scope(
    artifact: dict[str, Any],
    scope_id: str | None,
) -> None:
    """Enforce a CAS artifact's opaque owner binding.

    The string form is shared by browser sessions, API keys and non-browser
    channels.  Only its SHA-256 digest is persisted in the manifest.
    """

    metadata = artifact.get("metadata")
    scope_key = metadata.get("scope_key") if isinstance(metadata, dict) else None
    if scope_key is None:
        # Pre-scope manifests are retained in CAS for controlled migration,
        # but are quarantined from every public HTTP surface.  Treating them
        # as not found avoids both cross-tenant disclosure and existence leaks.
        raise ArtifactNotFound("artifact_not_found")
    expected = hashlib.sha256(scope_id.encode()).hexdigest() if scope_id else ""
    if not isinstance(scope_key, str) or not hmac.compare_digest(scope_key, expected):
        raise ArtifactNotFound("artifact_not_found")


def _http_error(exc: ArtifactStoreError) -> HTTPException:
    if isinstance(exc, (ArtifactNotFound, ArtifactValidationError)):
        return HTTPException(status_code=404, detail="Artifact not found")
    if isinstance(exc, ArtifactConflict):
        return HTTPException(status_code=409, detail="Artifact revision conflict")
    return HTTPException(status_code=409, detail="Artifact integrity check failed")


@router.get("/api/v1/artifacts/{artifact_id}")
@router.get("/v1/artifacts/{artifact_id}", include_in_schema=False)
async def artifact_content(
    artifact_id: str,
    revision: int | None = Query(default=None, ge=1),
    download: bool = False,
    scope_id: str | None = Depends(resolve_optional_public_scope),
):
    try:
        store = get_artifact_store()
        _assert_artifact_scope(store.get(artifact_id, revision=revision), scope_id)
        stored = store.open(artifact_id, revision=revision)
    except ArtifactStoreError as exc:
        raise _http_error(exc) from exc
    artifact = stored.manifest
    headers = {
        "ETag": f'"{artifact["sha256"]}"',
        "X-Artifact-Id": artifact["id"],
        "X-Artifact-Revision": str(artifact["revision"]),
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": (
            "private, max-age=31536000, immutable" if revision is not None else "private, no-cache"
        ),
    }
    if download:
        quoted = quote(str(artifact["filename"]), safe="")
        headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{quoted}"
    return Response(content=stored.content, media_type=artifact["mime_type"], headers=headers)


@router.get("/api/v1/artifacts/{artifact_id}/reopen")
@router.get("/v1/artifacts/{artifact_id}/reopen", include_in_schema=False)
async def artifact_reopen(
    artifact_id: str,
    revision: int | None = Query(default=None, ge=1),
    scope_id: str | None = Depends(resolve_optional_public_scope),
):
    try:
        store = get_artifact_store()
        artifact = store.get(artifact_id, revision=revision)
        _assert_artifact_scope(artifact, scope_id)
        reopened = store.reopen(artifact_id, revision=revision)
        reopened["artifact"] = _public_http_artifact_manifest(reopened["artifact"])
        if artifact.get("type") in {"site.bundle", "app.bundle"} and scope_id:
            # Preview bearer capabilities are intentionally short lived and
            # are not persisted in the immutable manifest.  Reopen issues a
            # fresh scoped URL so project history/reload never reuses an
            # expired token or tries to reconstruct one in the browser.
            from app.tool_router import _signed_preview_url

            reopened["preview_url"] = _signed_preview_url(artifact_id, scope_id)
        return reopened
    except ArtifactStoreError as exc:
        raise _http_error(exc) from exc


@router.get("/api/v1/artifacts/{artifact_id}/history")
@router.get("/v1/artifacts/{artifact_id}/history", include_in_schema=False)
async def artifact_history(
    artifact_id: str,
    scope_id: str | None = Depends(resolve_optional_public_scope),
):
    try:
        store = get_artifact_store()
        _assert_artifact_scope(store.get(artifact_id), scope_id)
        history = store.history(artifact_id)
        return {
            "artifact_id": artifact_id,
            "items": [_public_http_artifact_manifest(item) for item in history],
            "total": len(history),
        }
    except ArtifactStoreError as exc:
        raise _http_error(exc) from exc
