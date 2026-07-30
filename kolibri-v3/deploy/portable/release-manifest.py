#!/usr/bin/env python3
"""Build and verify deterministic Kolibri V3 portable release archives."""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import io
import json
import os
import platform
import re
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO, NoReturn


FORMAT = "kolibri-v3-portable-v2"
BUILDER_VERSION = "2"
PACKAGE_ROOT = "kolibri-v3"
CANONICAL_RELEASE_LANE = "canonical-portable-only"
CONTENT_MANIFEST = "RELEASE_CONTENTS.sha256"
MIGRATION_MANIFEST = "MIGRATIONS.sha256"
PROVENANCE_FILE = "RELEASE_PROVENANCE.json"
INTERNAL_METADATA = frozenset(
    {CONTENT_MANIFEST, MIGRATION_MANIFEST, PROVENANCE_FILE}
)
REQUIRED_FILES = frozenset(
    {
        "app/layout.tsx",
        "app/api/live/route.ts",
        "backend/app/main.py",
        "backend/app/product_run_worker.py",
        "backend/app/provider_enrollment_worker.py",
        "backend/app/release_monitor.py",
        "backend/app/runtime_readiness.py",
        "backend/migrations/033_platform_admin_control_plane.sql",
        "backend/migrations/034_trusted_agent_control_plane.sql",
        "backend/migrations/035_platform_audit_read_capability.sql",
        "backend/migrations/036_trusted_agent_execution_binding.sql",
        "backend/migrations/037_trusted_agent_lease_lifecycle.sql",
        "backend/migrations/038_product_entitlement_projection.sql",
        "backend/migrations/039_durable_direct_run_outbox.sql",
        "backend/migrations/040_bounded_attachments.sql",
        "backend/migrations/041_generated_image_artifacts.sql",
        "backend/migrations/042_storage_admin_control_plane.sql",
        "backend/migrations/043_storage_admin_restore_reconcile.sql",
        "backend/migrations/044_runtime_worker_heartbeats.sql",
        "contracts/generated/v1/manifest.json",
        "contracts/v1/verticals/examples/construction-estimates.json",
        "contracts/v1/verticals/vertical-pack-manifest.schema.json",
        "backend/requirements.txt",
        "deploy/portable/build-release.sh",
        "deploy/portable/database-rehearsal.py",
        "deploy/portable/install-contract.py",
        "deploy/portable/install.sh",
        "deploy/portable/release-manifest.py",
        "deploy/portable/smoke-test.sh",
        "deploy/workers/kolibri-v3-estimate-reconciliation-audit.service.in",
        "deploy/workers/kolibri-v3-product-run-worker.service.in",
        "deploy/workers/kolibri-v3-provider-enrollment-worker.service.in",
        "deploy/workers/worker_launcher.py",
        "deploy/workers/workers.env.example",
        "generated/contracts-v1.ts",
        "package-lock.json",
        "package.json",
        "server/contracts_runtime.py",
        "server/generate_contract_manifest.py",
    }
)
FORBIDDEN_ALTERNATE_RELEASE_PATHS = frozenset(
    {
        "deploy/install-home.sh",
        "deploy/kolibri-v3-backend.service",
        "deploy/kolibri-v3-frontend.service",
        "deploy/nginx-kolibriai.conf",
    }
)
LEGACY_COORDINATOR_PATH = "ops/release_kolibri_v3_product.sh"
LEGACY_COORDINATOR_TOMBSTONE_SHA256 = (
    "97d8fde02789f1ec048d855cc2f252dd6676d3f8c24cb93018c1f060a14062bf"
)
FORBIDDEN_REPOSITORY_RELEASE_PREFIXES = (
    "ops/release/kolibri-v3-baremetal/",
    "ops/release/product-agent/",
)
CONTRACT_MANIFEST_PATH = "contracts/generated/v1/manifest.json"
CONTRACT_SOURCE_PREFIX = "contracts/v1/"
CONTRACT_OUTPUTS = (
    "generated/contracts-v1.ts",
    "server/contracts_runtime.py",
)
MIGRATION_PATTERN = re.compile(
    r"^backend/migrations/(?P<version>[0-9]{3,})_[^/]+[.]sql$"
)
GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
RELEASE_ID_PATTERN = re.compile(
    r"^kolibri-v3-[0-9a-f]{12}-[0-9a-f]{12}$"
)
ARCHIVE_NAME_PATTERN = re.compile(
    r"^kolibri-v3-[0-9a-f]{12}-[0-9a-f]{12}[.]tar[.]gz$"
)
PRIVATE_KEY_PATTERN = re.compile(
    br"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
)
SECRET_TOKEN_PATTERNS = (
    ("openai_key", re.compile(br"sk-[A-Za-z0-9_-]{20,}")),
    ("anthropic_key", re.compile(br"sk-ant-[A-Za-z0-9_-]{20,}")),
    ("github_token", re.compile(br"gh[pousr]_[A-Za-z0-9]{20,}")),
    ("gitlab_token", re.compile(br"glpat-[A-Za-z0-9_-]{20,}")),
    ("slack_token", re.compile(br"xox[baprs]-[A-Za-z0-9-]{20,}")),
    ("npm_token", re.compile(br"npm_[A-Za-z0-9]{20,}")),
    ("stripe_live_key", re.compile(br"sk_live_[A-Za-z0-9]{16,}")),
    ("google_api_key", re.compile(br"AIza[A-Za-z0-9_-]{35}")),
    ("digitalocean_token", re.compile(br"dop_v1_[0-9a-f]{64}")),
    ("huggingface_token", re.compile(br"hf_[A-Za-z0-9]{20,}")),
    (
        "telegram_bot_token",
        re.compile(br"(?<![0-9])[0-9]{8,10}:[A-Za-z0-9_-]{35}(?![A-Za-z0-9_-])"),
    ),
    ("aws_access_key", re.compile(br"AKIA[0-9A-Z]{16}")),
    (
        "jwt",
        re.compile(
            br"eyJ[A-Za-z0-9_-]{16,}[.]eyJ[A-Za-z0-9_-]{16,}"
            br"[.][A-Za-z0-9_-]{20,}"
        ),
    ),
    (
        "credential_assignment",
        re.compile(
            br"(?im)^[ \t]*(?:export[ \t]+)?"
            br"(?:OPENAI_API_KEY|ANTHROPIC_API_KEY|GOOGLE_API_KEY|"
            br"GITHUB_TOKEN|GITLAB_TOKEN|NPM_TOKEN|SLACK_TOKEN|"
            br"STRIPE_SECRET_KEY|TELEGRAM_BOT_TOKEN|"
            br"AWS_SECRET_ACCESS_KEY|AZURE_CLIENT_SECRET|"
            br"GOOGLE_APPLICATION_CREDENTIALS|CLIENT_SECRET|"
            br"PRIVATE_KEY)[ \t]*[:=][ \t]*[\"']?"
            br"[A-Za-z0-9_+./:@=-]{16,}"
        ),
    ),
    (
        "registry_auth_token",
        re.compile(
            br"(?im)^[ \t]*(?://[^ \t\r\n:]+/?:)?_authToken"
            br"[ \t]*=[ \t]*[A-Za-z0-9._~-]{16,}"
        ),
    ),
    (
        "cloud_account_key",
        re.compile(
            br"(?i)AccountKey=[A-Za-z0-9+/]{40,}={0,2}"
        ),
    ),
    (
        "basic_auth_url",
        re.compile(
            br"https?://[^ \t\r\n/:@]{1,128}:"
            br"[^ \t\r\n/@]{16,256}@"
        ),
    ),
)
FORBIDDEN_SUFFIXES = (
    ".db",
    ".jks",
    ".key",
    ".kdbx",
    ".keystore",
    ".mobileprovision",
    ".ovpn",
    ".p12",
    ".p8",
    ".pem",
    ".pfx",
    ".pyc",
    ".pyo",
    ".sqlite",
    ".sqlite3",
)
FORBIDDEN_CREDENTIAL_BASENAMES = frozenset(
    {
        ".netrc",
        ".npmrc",
        ".pypirc",
        "auth.json",
        "credentials.json",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
        "id_rsa",
        "service-account.json",
        "service_account.json",
    }
)
FORBIDDEN_PATH_PARTS = frozenset(
    {
        ".expo",
        ".next",
        ".pytest_cache",
        ".turbo",
        ".wrangler",
        "__pycache__",
        "coverage",
        "dist",
        "node_modules",
    }
)
MAX_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_PROVENANCE_BYTES = 128 * 1024


class ReleaseError(RuntimeError):
    """A bounded, user-facing release validation error."""


@dataclass(frozen=True)
class SourceFile:
    relative_path: str
    mode: int
    payload: bytes
    sha256: str


def fail(code: str, detail: str | None = None) -> NoReturn:
    suffix = f" {detail}" if detail else ""
    print(f"release_error={code}{suffix}", file=sys.stderr)
    raise SystemExit(3)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_handle(handle: BinaryIO) -> str:
    digest = hashlib.sha256()
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def sha256_file(path: Path) -> str:
    with path.open("rb") as handle:
        return sha256_handle(handle)


def git(repo: Path, *arguments: str, binary: bool = False) -> bytes | str:
    try:
        result = subprocess.run(
            ["git", "-C", os.fspath(repo), *arguments],
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ReleaseError(f"git_command_failed command={arguments[0]}") from exc
    if binary:
        return result.stdout
    return result.stdout.decode("utf-8").strip()


def normalize_project_path(project: str) -> str:
    normalized = project.strip("/")
    candidate = PurePosixPath(normalized)
    if normalized == ".":
        return normalized
    if (
        not normalized
        or candidate.is_absolute()
        or ".." in candidate.parts
        or normalized != candidate.as_posix()
        or candidate.name != PACKAGE_ROOT
    ):
        raise ReleaseError("invalid_project_path")
    return normalized


def audit_repository_release_lane(repo: Path, commit: str) -> str:
    resolved_commit = str(
        git(repo, "rev-parse", "--verify", f"{commit}^{{commit}}")
    )
    if not GIT_SHA_PATTERN.fullmatch(resolved_commit):
        raise ReleaseError("invalid_git_commit")
    listing = bytes(
        git(
            repo,
            "ls-tree",
            "-r",
            "-z",
            "--name-only",
            resolved_commit,
            binary=True,
        )
    )
    paths: set[str] = set()
    for raw_path in listing.split(b"\0"):
        if not raw_path:
            continue
        try:
            path = raw_path.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ReleaseError("repository_path_not_utf8") from exc
        candidate = PurePosixPath(path)
        if (
            not path
            or candidate.is_absolute()
            or ".." in candidate.parts
            or path != candidate.as_posix()
            or "\n" in path
            or "\r" in path
            or path in paths
        ):
            raise ReleaseError("unsafe_repository_path")
        paths.add(path)

    for path in sorted(paths):
        candidate = PurePosixPath(path)
        if path == LEGACY_COORDINATOR_PATH:
            payload = bytes(
                git(
                    repo,
                    "show",
                    f"{resolved_commit}:{path}",
                    binary=True,
                )
            )
            if sha256_bytes(payload) != LEGACY_COORDINATOR_TOMBSTONE_SHA256:
                raise ReleaseError(
                    f"legacy_release_tombstone_changed path={path}"
                )
            continue
        if (
            path.startswith("ops/release_kolibri_v3_")
            or any(
                path.startswith(prefix)
                for prefix in FORBIDDEN_REPOSITORY_RELEASE_PREFIXES
            )
            or (
                candidate.parent == PurePosixPath("ops/release")
                and re.match(r"^kolibri[_-]v3(?:[_-]|[.])", candidate.name)
            )
        ):
            raise ReleaseError(
                f"repository_alternate_release_lane_forbidden path={path}"
            )
    return resolved_commit


def assert_safe_source(item: SourceFile) -> None:
    path = PurePosixPath(item.relative_path)
    basename = path.name.lower()
    if item.relative_path in FORBIDDEN_ALTERNATE_RELEASE_PATHS:
        raise ReleaseError(
            f"alternate_release_lane_forbidden path={item.relative_path}"
        )
    if any(part.lower() == "kolibri-backend" for part in path.parts):
        raise ReleaseError(
            f"legacy_backend_forbidden path={item.relative_path}"
        )
    if (
        any(part.lower() in FORBIDDEN_PATH_PARTS for part in path.parts)
        or basename.endswith(FORBIDDEN_SUFFIXES)
        or basename in FORBIDDEN_CREDENTIAL_BASENAMES
        or basename == ".env"
        or (basename.startswith(".env.") and basename != ".env.example")
        or basename == "telegram.env"
    ):
        raise ReleaseError(
            f"secret_or_mutable_file_forbidden path={item.relative_path}"
        )
    if PRIVATE_KEY_PATTERN.search(item.payload):
        raise ReleaseError(
            f"private_key_material_forbidden path={item.relative_path}"
        )
    for label, pattern in SECRET_TOKEN_PATTERNS:
        if pattern.search(item.payload):
            raise ReleaseError(
                f"secret_token_material_forbidden path={item.relative_path} "
                f"kind={label}"
            )


def validate_contract_package(files: list[SourceFile]) -> None:
    files_by_path = {item.relative_path: item for item in files}
    manifest_item = files_by_path.get(CONTRACT_MANIFEST_PATH)
    if manifest_item is None:
        raise ReleaseError("contract_manifest_missing")
    if len(manifest_item.payload) > MAX_PROVENANCE_BYTES:
        raise ReleaseError("contract_manifest_too_large")
    try:
        manifest = json.loads(manifest_item.payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseError("contract_manifest_invalid_json") from exc
    schemas = manifest.get("schemas") if isinstance(manifest, dict) else None
    outputs = manifest.get("outputs") if isinstance(manifest, dict) else None
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema_id")
        != "kolibri.generated_contract_package_manifest"
        or manifest.get("schema_version") != "1.0"
        or not isinstance(schemas, list)
        or not schemas
        or manifest.get("schema_count") != len(schemas)
        or outputs != list(CONTRACT_OUTPUTS)
    ):
        raise ReleaseError("contract_manifest_invalid_shape")

    manifest_paths: set[str] = set()
    manifest_uris: set[str] = set()
    for entry in schemas:
        if not isinstance(entry, dict):
            raise ReleaseError("contract_manifest_entry_invalid")
        source_path = entry.get("source_path")
        schema_uri = entry.get("schema_uri")
        expected_digest = entry.get("sha256")
        if (
            not isinstance(source_path, str)
            or not source_path.startswith(CONTRACT_SOURCE_PREFIX)
            or not source_path.endswith(".schema.json")
            or PurePosixPath(source_path).is_absolute()
            or ".." in PurePosixPath(source_path).parts
            or source_path != PurePosixPath(source_path).as_posix()
            or not isinstance(schema_uri, str)
            or not schema_uri
            or not isinstance(expected_digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", expected_digest) is None
            or source_path in manifest_paths
            or schema_uri in manifest_uris
        ):
            raise ReleaseError("contract_manifest_entry_invalid")
        schema_item = files_by_path.get(source_path)
        if schema_item is None or schema_item.sha256 != expected_digest:
            raise ReleaseError(
                f"contract_schema_integrity_mismatch path={source_path}"
            )
        try:
            schema = json.loads(schema_item.payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ReleaseError(
                f"contract_schema_invalid_json path={source_path}"
            ) from exc
        if not isinstance(schema, dict) or schema.get("$id") != schema_uri:
            raise ReleaseError(
                f"contract_schema_identity_mismatch path={source_path}"
            )
        manifest_paths.add(source_path)
        manifest_uris.add(schema_uri)

    packaged_schema_paths = {
        path
        for path in files_by_path
        if path.startswith(CONTRACT_SOURCE_PREFIX)
        and path.endswith(".schema.json")
    }
    if manifest_paths != packaged_schema_paths:
        raise ReleaseError("contract_manifest_path_set_mismatch")
    for output in CONTRACT_OUTPUTS:
        if output not in files_by_path:
            raise ReleaseError(f"contract_output_missing path={output}")


def read_source_files(
    repo: Path, commit: str, project: str
) -> tuple[list[SourceFile], str, int]:
    resolved_commit = str(git(repo, "rev-parse", "--verify", f"{commit}^{{commit}}"))
    if not GIT_SHA_PATTERN.fullmatch(resolved_commit):
        raise ReleaseError("invalid_git_commit")
    treeish = (
        f"{resolved_commit}^{{tree}}"
        if project == "."
        else f"{resolved_commit}:{project}"
    )
    tree = str(git(repo, "rev-parse", "--verify", treeish))
    if not GIT_SHA_PATTERN.fullmatch(tree):
        raise ReleaseError("invalid_git_tree")
    commit_epoch_text = str(git(repo, "show", "-s", "--format=%ct", resolved_commit))
    if not commit_epoch_text.isdigit():
        raise ReleaseError("invalid_git_commit_time")

    listing = bytes(
        git(
            repo,
            "ls-tree",
            "-r",
            "-z",
            "--full-tree",
            resolved_commit,
            "--",
            project,
            binary=True,
        )
    )
    prefix = "" if project == "." else f"{project}/"
    files: list[SourceFile] = []
    for raw_record in listing.split(b"\0"):
        if not raw_record:
            continue
        try:
            metadata, raw_path = raw_record.split(b"\t", 1)
            mode_text, object_type, object_id = metadata.decode("ascii").split()
            full_path = raw_path.decode("utf-8")
        except (UnicodeDecodeError, ValueError) as exc:
            raise ReleaseError("invalid_git_tree_record") from exc
        if prefix and not full_path.startswith(prefix):
            raise ReleaseError("git_tree_path_outside_project")
        relative_path = full_path[len(prefix) :] if prefix else full_path
        pure_path = PurePosixPath(relative_path)
        if (
            not relative_path
            or pure_path.is_absolute()
            or ".." in pure_path.parts
            or relative_path != pure_path.as_posix()
            or "\n" in relative_path
            or "\r" in relative_path
        ):
            raise ReleaseError("unsafe_source_path")
        if object_type != "blob" or mode_text not in {"100644", "100755"}:
            raise ReleaseError(
                f"unsupported_source_entry path={relative_path} mode={mode_text}"
            )
        payload = bytes(git(repo, "cat-file", "blob", object_id, binary=True))
        item = SourceFile(
            relative_path=relative_path,
            mode=0o755 if mode_text == "100755" else 0o644,
            payload=payload,
            sha256=sha256_bytes(payload),
        )
        assert_safe_source(item)
        files.append(item)
    files.sort(key=lambda item: item.relative_path)
    if not files:
        raise ReleaseError("empty_project_tree")
    return files, tree, int(commit_epoch_text)


def manifest_payload(files: list[SourceFile]) -> bytes:
    return "".join(
        f"{item.sha256}  {item.relative_path}\n" for item in files
    ).encode("utf-8")


def migration_records(files: list[SourceFile]) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for item in files:
        match = MIGRATION_PATTERN.fullmatch(item.relative_path)
        if match:
            records.append(
                {
                    "version": match.group("version"),
                    "path": item.relative_path,
                    "sha256": item.sha256,
                }
            )
    if not records:
        raise ReleaseError("migration_manifest_empty")
    records.sort(key=lambda item: (int(item["version"]), item["path"]))
    versions = [item["version"] for item in records]
    if len(versions) != len(set(versions)):
        raise ReleaseError("duplicate_migration_version")
    return records


def migration_manifest_payload(records: list[dict[str, str]]) -> bytes:
    return "".join(
        f"{record['sha256']}  {record['path']}\n" for record in records
    ).encode("utf-8")


def provenance_payload(
    *,
    release_id: str,
    commit: str,
    tree: str,
    commit_epoch: int,
    content_digest: str,
    gate_input_digest: str,
    records: list[dict[str, str]],
    migration_manifest_digest: str,
    git_version: str,
) -> bytes:
    built_at = dt.datetime.fromtimestamp(
        commit_epoch, tz=dt.UTC
    ).isoformat().replace("+00:00", "Z")
    document = {
        "format": FORMAT,
        "release_id": release_id,
        "source_commit": commit,
        "source_tree_sha256": content_digest,
        "gate_input_digest": gate_input_digest,
        "built_at": built_at,
        "built_at_basis": "git_commit_time_for_reproducibility",
        "dirty": False,
        "builder": {
            "name": "kolibri-v3-portable-release-manifest",
            "version": BUILDER_VERSION,
            "python": platform.python_version(),
            "git": git_version,
        },
        "source": {
            "kind": "committed-git-tree",
            "git_commit_sha": commit,
            "git_tree_sha": tree,
            "git_commit_epoch": commit_epoch,
            "project_path": PACKAGE_ROOT,
            "source_tree_sha256": content_digest,
        },
        "content": {
            "digest_algorithm": "sha256",
            "digest": content_digest,
            "manifest": CONTENT_MANIFEST,
            "path_basis": f"{PACKAGE_ROOT}-relative-posix",
        },
        "gates": {
            "input_digest": gate_input_digest,
            "release_lane": CANONICAL_RELEASE_LANE,
            "status": "requires-smoke-test",
        },
        "package": {
            "sha256_location": "adjacent .manifest.json and .sha256 sidecars",
        },
        "components": {
            "web": "app",
            "backend": "backend",
            "persistent_database": "/opt/kolibri-v3/var/kolibri-v3.db",
            "release_root": "/opt/kolibri-v3/releases",
        },
        "activation_preconditions": {
            "database_owner": "kolibri-service-user",
            "database_mode": "0600",
            "database_sidecars": [
                "kolibri-v3.db-wal",
                "kolibri-v3.db-shm",
            ],
            "database_sidecar_mode": "0600",
            "backend_systemd_umask": "0077",
            "worker_gate": "fail-closed-before-activation",
        },
        "migrations": {
            "directory": "backend/migrations",
            "minimum_version": records[0]["version"],
            "maximum_version": records[-1]["version"],
            "count": len(records),
            "manifest": MIGRATION_MANIFEST,
            "manifest_sha256": migration_manifest_digest,
            "entries": records,
            "rollback_policy": "expand-additive-only",
        },
    }
    return (
        json.dumps(
            document,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def tar_info(name: str, size: int, mode: int) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name=name)
    info.size = size
    info.mode = mode
    info.mtime = 0
    info.uid = 0
    info.gid = 0
    info.uname = "root"
    info.gname = "root"
    info.type = tarfile.REGTYPE
    return info


def write_archive(
    archive: Path,
    files: list[SourceFile],
    metadata: dict[str, bytes],
) -> None:
    archive.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=archive.parent,
        prefix=f".{archive.name}.",
        delete=False,
    ) as temporary:
        temporary_path = Path(temporary.name)
    try:
        with temporary_path.open("wb") as raw_output:
            with gzip.GzipFile(
                filename="",
                mode="wb",
                fileobj=raw_output,
                compresslevel=9,
                mtime=0,
            ) as compressed:
                with tarfile.open(
                    fileobj=compressed,
                    mode="w",
                    format=tarfile.GNU_FORMAT,
                ) as archive_file:
                    entries = {
                        item.relative_path: (item.payload, item.mode)
                        for item in files
                    }
                    entries.update(
                        {name: (payload, 0o644) for name, payload in metadata.items()}
                    )
                    for relative_path in sorted(entries):
                        payload, mode = entries[relative_path]
                        package_path = f"{PACKAGE_ROOT}/{relative_path}"
                        archive_file.addfile(
                            tar_info(package_path, len(payload), mode),
                            io.BytesIO(payload),
                        )
        os.chmod(temporary_path, 0o644)
        os.replace(temporary_path, archive)
    finally:
        temporary_path.unlink(missing_ok=True)


def atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as temporary:
        temporary.write(payload)
        temporary_path = Path(temporary.name)
    try:
        os.chmod(temporary_path, 0o644)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def build(arguments: argparse.Namespace) -> None:
    repo = arguments.repo.resolve(strict=True)
    project = normalize_project_path(arguments.project)
    commit = str(git(repo, "rev-parse", "--verify", f"{arguments.commit}^{{commit}}"))
    audit_repository_release_lane(repo, commit)
    files, tree, commit_epoch = read_source_files(repo, commit, project)
    paths = {item.relative_path for item in files}
    missing = sorted(REQUIRED_FILES - paths)
    if missing:
        raise ReleaseError(f"required_source_missing path={missing[0]}")
    validate_contract_package(files)

    content_manifest = manifest_payload(files)
    content_digest = sha256_bytes(content_manifest)
    migrations = migration_records(files)
    migrations_payload = migration_manifest_payload(migrations)
    migrations_digest = sha256_bytes(migrations_payload)
    gate_input_digest = sha256_bytes(
        content_manifest + b"\0" + migrations_payload
    )
    release_id = f"kolibri-v3-{commit[:12]}-{content_digest[:12]}"
    if not RELEASE_ID_PATTERN.fullmatch(release_id):
        raise ReleaseError("invalid_release_identity")
    provenance = provenance_payload(
        release_id=release_id,
        commit=commit,
        tree=tree,
        commit_epoch=commit_epoch,
        content_digest=content_digest,
        gate_input_digest=gate_input_digest,
        records=migrations,
        migration_manifest_digest=migrations_digest,
        git_version=str(git(repo, "--version")),
    )

    output_dir = arguments.output_dir.resolve()
    archive = output_dir / f"{release_id}.tar.gz"
    write_archive(
        archive,
        files,
        {
            CONTENT_MANIFEST: content_manifest,
            MIGRATION_MANIFEST: migrations_payload,
            PROVENANCE_FILE: provenance,
        },
    )
    package_sha256 = sha256_file(archive)
    sidecar = {
        "format": FORMAT,
        "release_id": release_id,
        "archive": archive.name,
        "package_sha256": package_sha256,
        "source_commit": commit,
        "content_digest": content_digest,
        "source_tree_sha256": content_digest,
        "gate_input_digest": gate_input_digest,
        "git_commit_sha": commit,
        "git_tree_sha": tree,
        "migration_minimum_version": migrations[0]["version"],
        "migration_maximum_version": migrations[-1]["version"],
        "migration_count": len(migrations),
        "migration_manifest_sha256": migrations_digest,
        "release_lane": CANONICAL_RELEASE_LANE,
        "dirty": False,
    }
    sidecar_payload = (
        json.dumps(sidecar, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    manifest_path = Path(f"{archive}.manifest.json")
    checksum_path = Path(f"{archive}.sha256")
    atomic_write(manifest_path, sidecar_payload)
    atomic_write(
        checksum_path,
        f"{package_sha256}  {archive.name}\n".encode("ascii"),
    )
    print(f"release_id={release_id}")
    print(f"release_archive={archive}")
    print(f"release_manifest={manifest_path}")
    print(f"release_sha256_file={checksum_path}")
    print(f"release_sha256={package_sha256}")
    print(f"release_content_digest={content_digest}")
    print(f"release_gate_input_digest={gate_input_digest}")
    print(f"release_lane={CANONICAL_RELEASE_LANE}")
    print(f"release_commit={commit}")
    print(f"release_tree={tree}")
    print(f"release_migration_min={migrations[0]['version']}")
    print(f"release_migration_max={migrations[-1]['version']}")


def parse_hash_manifest(payload: bytes, label: str) -> dict[str, str]:
    if len(payload) > MAX_MANIFEST_BYTES:
        raise ReleaseError(f"{label}_too_large")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ReleaseError(f"{label}_not_utf8") from exc
    records: dict[str, str] = {}
    for line in text.splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([^\r\n]+)", line)
        if not match:
            raise ReleaseError(f"{label}_invalid")
        digest, relative_path = match.groups()
        candidate = PurePosixPath(relative_path)
        if (
            candidate.is_absolute()
            or ".." in candidate.parts
            or relative_path != candidate.as_posix()
            or relative_path in records
        ):
            raise ReleaseError(f"{label}_unsafe_path")
        records[relative_path] = digest
    if not records:
        raise ReleaseError(f"{label}_empty")
    return records


def read_archive_handle(
    archive_handle: BinaryIO,
) -> dict[str, tuple[bytes, int]]:
    entries: dict[str, tuple[bytes, int]] = {}
    try:
        with tarfile.open(
            fileobj=archive_handle,
            mode="r:gz",
        ) as release_archive:
            for member in release_archive:
                if not member.isfile():
                    raise ReleaseError(
                        f"unsupported_archive_entry path={member.name}"
                    )
                candidate = PurePosixPath(member.name)
                if (
                    candidate.is_absolute()
                    or ".." in candidate.parts
                    or not member.name.startswith(f"{PACKAGE_ROOT}/")
                ):
                    raise ReleaseError("archive_path_outside_package")
                relative_path = member.name[len(PACKAGE_ROOT) + 1 :]
                relative_candidate = PurePosixPath(relative_path)
                if (
                    not relative_path
                    or relative_path != relative_candidate.as_posix()
                    or "\n" in relative_path
                    or "\r" in relative_path
                    or relative_path in entries
                ):
                    raise ReleaseError("duplicate_or_empty_archive_path")
                handle = release_archive.extractfile(member)
                if handle is None:
                    raise ReleaseError("archive_entry_unreadable")
                payload = handle.read()
                item = SourceFile(
                    relative_path=relative_path,
                    mode=member.mode & 0o777,
                    payload=payload,
                    sha256=sha256_bytes(payload),
                )
                if relative_path not in INTERNAL_METADATA:
                    assert_safe_source(item)
                entries[relative_path] = (payload, member.mode & 0o777)
    except (OSError, tarfile.TarError) as exc:
        raise ReleaseError("archive_unreadable") from exc
    return entries


def read_archive(archive: Path) -> dict[str, tuple[bytes, int]]:
    try:
        with archive.open("rb") as archive_handle:
            return read_archive_handle(archive_handle)
    except OSError as exc:
        raise ReleaseError("archive_unreadable") from exc


def load_json(path: Path, max_bytes: int) -> dict[str, object]:
    try:
        with path.open("rb") as handle:
            try:
                handle.seek(0)
                payload = handle.read(max_bytes + 1)
            finally:
                handle.seek(0)
    except OSError as exc:
        raise ReleaseError(f"manifest_unreadable path={path}") from exc
    if len(payload) > max_bytes:
        raise ReleaseError("manifest_too_large")
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseError("manifest_invalid_json") from exc
    if not isinstance(document, dict):
        raise ReleaseError("manifest_invalid_shape")
    return document


def verify(arguments: argparse.Namespace) -> None:
    if arguments.archive_name:
        if (
            not ARCHIVE_NAME_PATTERN.fullmatch(arguments.archive_name)
            or Path(arguments.archive_name).name != arguments.archive_name
            or arguments.manifest is None
            or arguments.checksum is None
        ):
            raise ReleaseError("archive_fd_contract_invalid")
        archive = arguments.archive
        archive_name = arguments.archive_name
        manifest_path = arguments.manifest
        checksum_path = arguments.checksum
    else:
        archive = arguments.archive.resolve(strict=True)
        archive_name = archive.name
        manifest_path = (
            arguments.manifest.resolve(strict=True)
            if arguments.manifest
            else Path(f"{archive}.manifest.json").resolve(strict=True)
        )
        checksum_path = (
            arguments.checksum.resolve(strict=True)
            if arguments.checksum
            else Path(f"{archive}.sha256").resolve(strict=True)
        )
    sidecar = load_json(manifest_path, MAX_PROVENANCE_BYTES)
    try:
        with archive.open("rb") as archive_handle:
            try:
                archive_handle.seek(0)
                package_sha256 = sha256_handle(archive_handle)
                archive_handle.seek(0)
                entries = read_archive_handle(archive_handle)
            finally:
                archive_handle.seek(0)
    except OSError as exc:
        raise ReleaseError("archive_unreadable") from exc
    if sidecar.get("format") != FORMAT:
        raise ReleaseError("manifest_format_mismatch")
    if sidecar.get("archive") != archive_name:
        raise ReleaseError("manifest_archive_mismatch")
    if sidecar.get("package_sha256") != package_sha256:
        raise ReleaseError("package_sha256_mismatch")
    try:
        with checksum_path.open("r", encoding="ascii") as checksum_handle:
            try:
                checksum_handle.seek(0)
                checksum_text = checksum_handle.read(1024)
            finally:
                checksum_handle.seek(0)
    except OSError as exc:
        raise ReleaseError("checksum_unreadable") from exc
    if checksum_text != f"{package_sha256}  {archive_name}\n":
        raise ReleaseError("checksum_file_mismatch")

    missing = sorted(REQUIRED_FILES - set(entries))
    if missing:
        raise ReleaseError(f"required_package_file_missing path={missing[0]}")
    for metadata_file in INTERNAL_METADATA:
        if metadata_file not in entries:
            raise ReleaseError(
                f"release_metadata_missing path={metadata_file}"
            )
    validate_contract_package(
        [
            SourceFile(
                relative_path=relative_path,
                mode=mode,
                payload=payload,
                sha256=sha256_bytes(payload),
            )
            for relative_path, (payload, mode) in entries.items()
            if relative_path not in INTERNAL_METADATA
        ]
    )

    content_records = parse_hash_manifest(
        entries[CONTENT_MANIFEST][0], "content_manifest"
    )
    packaged_source_paths = set(entries) - INTERNAL_METADATA
    if set(content_records) != packaged_source_paths:
        raise ReleaseError("content_manifest_path_set_mismatch")
    for relative_path, expected_digest in content_records.items():
        if sha256_bytes(entries[relative_path][0]) != expected_digest:
            raise ReleaseError(
                f"content_manifest_digest_mismatch path={relative_path}"
            )
    canonical_content_manifest = "".join(
        f"{content_records[path]}  {path}\n" for path in sorted(content_records)
    ).encode("utf-8")
    if canonical_content_manifest != entries[CONTENT_MANIFEST][0]:
        raise ReleaseError("content_manifest_not_canonical")
    content_digest = sha256_bytes(canonical_content_manifest)

    actual_migrations: list[dict[str, str]] = []
    for relative_path in sorted(packaged_source_paths):
        match = MIGRATION_PATTERN.fullmatch(relative_path)
        if match:
            actual_migrations.append(
                {
                    "version": match.group("version"),
                    "path": relative_path,
                    "sha256": content_records[relative_path],
                }
            )
    actual_migrations.sort(key=lambda item: (int(item["version"]), item["path"]))
    if not actual_migrations:
        raise ReleaseError("migration_manifest_empty")
    versions = [item["version"] for item in actual_migrations]
    if len(versions) != len(set(versions)):
        raise ReleaseError("duplicate_migration_version")
    expected_migration_manifest = migration_manifest_payload(actual_migrations)
    if entries[MIGRATION_MANIFEST][0] != expected_migration_manifest:
        raise ReleaseError("migration_manifest_mismatch")
    migrations_digest = sha256_bytes(expected_migration_manifest)
    gate_input_digest = sha256_bytes(
        canonical_content_manifest + b"\0" + expected_migration_manifest
    )

    if len(entries[PROVENANCE_FILE][0]) > MAX_PROVENANCE_BYTES:
        raise ReleaseError("provenance_too_large")
    try:
        provenance = json.loads(entries[PROVENANCE_FILE][0])
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseError("provenance_invalid_json") from exc
    if not isinstance(provenance, dict):
        raise ReleaseError("provenance_invalid_shape")

    release_id = sidecar.get("release_id")
    commit = sidecar.get("git_commit_sha")
    tree = sidecar.get("git_tree_sha")
    if not isinstance(release_id, str) or not RELEASE_ID_PATTERN.fullmatch(
        release_id
    ):
        raise ReleaseError("release_identity_invalid")
    if not isinstance(commit, str) or not GIT_SHA_PATTERN.fullmatch(commit):
        raise ReleaseError("release_commit_invalid")
    if not isinstance(tree, str) or not GIT_SHA_PATTERN.fullmatch(tree):
        raise ReleaseError("release_tree_invalid")
    expected_release_id = f"kolibri-v3-{commit[:12]}-{content_digest[:12]}"
    if release_id != expected_release_id:
        raise ReleaseError("release_identity_mismatch")

    source = provenance.get("source")
    content = provenance.get("content")
    gates = provenance.get("gates")
    components = provenance.get("components")
    activation = provenance.get("activation_preconditions")
    migrations = provenance.get("migrations")
    if (
        provenance.get("format") != FORMAT
        or provenance.get("release_id") != release_id
        or provenance.get("source_commit") != commit
        or provenance.get("source_tree_sha256") != content_digest
        or provenance.get("gate_input_digest") != gate_input_digest
        or provenance.get("dirty") is not False
        or not isinstance(source, dict)
        or source.get("git_commit_sha") != commit
        or source.get("git_tree_sha") != tree
        or source.get("project_path") != PACKAGE_ROOT
        or source.get("source_tree_sha256") != content_digest
        or not isinstance(content, dict)
        or content.get("digest") != content_digest
        or content.get("path_basis") != f"{PACKAGE_ROOT}-relative-posix"
        or not isinstance(gates, dict)
        or gates.get("input_digest") != gate_input_digest
        or gates.get("release_lane") != CANONICAL_RELEASE_LANE
        or not isinstance(components, dict)
        or components.get("web") != "app"
        or components.get("backend") != "backend"
        or components.get("persistent_database")
        != "/opt/kolibri-v3/var/kolibri-v3.db"
        or components.get("release_root") != "/opt/kolibri-v3/releases"
        or not isinstance(activation, dict)
        or activation.get("database_mode") != "0600"
        or activation.get("database_sidecar_mode") != "0600"
        or activation.get("backend_systemd_umask") != "0077"
        or activation.get("worker_gate") != "fail-closed-before-activation"
        or not isinstance(migrations, dict)
        or migrations.get("minimum_version") != actual_migrations[0]["version"]
        or migrations.get("maximum_version") != actual_migrations[-1]["version"]
        or migrations.get("count") != len(actual_migrations)
        or migrations.get("manifest_sha256") != migrations_digest
        or migrations.get("entries") != actual_migrations
        or migrations.get("rollback_policy") != "expand-additive-only"
    ):
        raise ReleaseError("provenance_mismatch")

    sidecar_expectations = {
        "source_commit": commit,
        "content_digest": content_digest,
        "source_tree_sha256": content_digest,
        "gate_input_digest": gate_input_digest,
        "migration_minimum_version": actual_migrations[0]["version"],
        "migration_maximum_version": actual_migrations[-1]["version"],
        "migration_count": len(actual_migrations),
        "migration_manifest_sha256": migrations_digest,
        "release_lane": CANONICAL_RELEASE_LANE,
        "dirty": False,
    }
    for key, expected_value in sidecar_expectations.items():
        if sidecar.get(key) != expected_value:
            raise ReleaseError(f"manifest_field_mismatch field={key}")

    print("release_verify=ok")
    print(f"release_id={release_id}")
    print(f"release_sha256={package_sha256}")
    print(f"release_content_digest={content_digest}")
    print(f"release_gate_input_digest={gate_input_digest}")
    print(f"release_commit={commit}")
    print(f"release_tree={tree}")
    print(f"release_migration_min={actual_migrations[0]['version']}")
    print(f"release_migration_max={actual_migrations[-1]['version']}")


def audit_repository_command(arguments: argparse.Namespace) -> None:
    repo = arguments.repo.resolve(strict=True)
    commit = audit_repository_release_lane(repo, arguments.commit)
    print("repository_release_lane=ok")
    print(f"release_lane={CANONICAL_RELEASE_LANE}")
    print(f"release_commit={commit}")


def parser() -> argparse.ArgumentParser:
    release_parser = argparse.ArgumentParser(
        description="Build or verify Kolibri V3 portable releases."
    )
    commands = release_parser.add_subparsers(dest="command", required=True)
    build_parser = commands.add_parser("build")
    build_parser.add_argument("--repo", required=True, type=Path)
    build_parser.add_argument("--project", default=PACKAGE_ROOT)
    build_parser.add_argument("--commit", default="HEAD")
    build_parser.add_argument("--output-dir", required=True, type=Path)
    build_parser.set_defaults(handler=build)

    verify_parser = commands.add_parser("verify")
    verify_parser.add_argument("--archive", required=True, type=Path)
    verify_parser.add_argument("--archive-name")
    verify_parser.add_argument("--manifest", type=Path)
    verify_parser.add_argument("--checksum", type=Path)
    verify_parser.set_defaults(handler=verify)

    audit_parser = commands.add_parser("audit-repository")
    audit_parser.add_argument("--repo", required=True, type=Path)
    audit_parser.add_argument("--commit", default="HEAD")
    audit_parser.set_defaults(handler=audit_repository_command)
    return release_parser


def main() -> int:
    arguments = parser().parse_args()
    try:
        arguments.handler(arguments)
    except ReleaseError as exc:
        fail(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
