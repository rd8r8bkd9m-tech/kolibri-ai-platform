#!/usr/bin/env python3
"""Kolibri skills registry and local sync installer.

The sync path intentionally accepts only local filesystem sources. Remote
workers install code that was already materialized by a trusted release process
and recorded in a registry with a content hash.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, unquote


SCHEMA_VERSION = 1
INSTALL_MANIFEST = ".kolibri-skill-install.json"
SKILL_METADATA_FILES = ("skill.json", "SKILL.json")


class SkillSyncError(RuntimeError):
    """Raised for expected registry/install contract failures."""


class SkillEntry:
    def __init__(self, name: str, version: str, source_path: Path, sha256_value: str, description: str = ""):
        self.name = name
        self.version = version
        self.source_path = source_path
        self.sha256 = sha256_value
        self.description = description


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SkillSyncError(f"invalid JSON in {path}: {exc}") from exc


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        tmp_path = Path(handle.name)
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(tmp_path, path)


def sanitize_name(value: str) -> str:
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-")
    cleaned = "".join(ch if ch in allowed else "-" for ch in value.strip())
    if not cleaned or cleaned in {".", ".."}:
        raise SkillSyncError(f"invalid skill name: {value!r}")
    return cleaned


def parse_version(value: str) -> tuple[tuple[int, Any], ...]:
    parts: list[tuple[int, Any]] = []
    for part in value.replace("-", ".").split("."):
        if part.isdigit():
            parts.append((0, int(part)))
        else:
            parts.append((1, part))
    return tuple(parts)


def version_cmp(left: str, right: str) -> int:
    left_parts = parse_version(left)
    right_parts = parse_version(right)
    return (left_parts > right_parts) - (left_parts < right_parts)


def resolve_source_path(raw: str, base_dir: Path, source_root: Path | None = None) -> Path:
    parsed = urlparse(raw)
    if parsed.scheme in {"http", "https", "git", "ssh"}:
        raise SkillSyncError(f"network skill sources are forbidden: {raw}")
    if parsed.scheme and parsed.scheme != "file":
        raise SkillSyncError(f"unsupported skill source scheme {parsed.scheme!r}: {raw}")

    if parsed.scheme == "file":
        candidate = Path(unquote(parsed.path))
    else:
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = base_dir / candidate
    resolved = candidate.resolve()
    if source_root is not None:
        root = source_root.resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise SkillSyncError(f"source path escapes allowed root {root}: {resolved}") from exc
    return resolved


def iter_regular_files(root: Path) -> list[Path]:
    if not root.is_dir():
        raise SkillSyncError(f"skill source is not a directory: {root}")
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise SkillSyncError(f"symlinks are forbidden in skill bundles: {path}")
        if path.is_file():
            files.append(path)
    if not files:
        raise SkillSyncError(f"skill source has no files: {root}")
    return files


def tree_sha256(root: Path) -> str:
    digest = sha256()
    for path in iter_regular_files(root):
        rel = path.relative_to(root).as_posix()
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def list_bundle_files(root: Path) -> list[dict[str, Any]]:
    files = []
    for path in iter_regular_files(root):
        rel = path.relative_to(root).as_posix()
        files.append({"path": rel, "sha256": sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size})
    return files


def read_skill_metadata(skill_dir: Path) -> dict[str, Any]:
    for metadata_name in SKILL_METADATA_FILES:
        metadata_path = skill_dir / metadata_name
        if metadata_path.is_file():
            metadata = load_json(metadata_path)
            if not isinstance(metadata.get("name"), str) or not isinstance(metadata.get("version"), str):
                raise SkillSyncError(f"{metadata_path} must include string name and version")
            return metadata
    raise SkillSyncError(f"missing skill metadata file in {skill_dir}; expected one of {', '.join(SKILL_METADATA_FILES)}")


def build_registry(source_root: Path) -> dict[str, Any]:
    root = source_root.resolve()
    skills: dict[str, Any] = {}
    for child in sorted(path for path in root.iterdir() if path.is_dir()):
        metadata = read_skill_metadata(child)
        name = sanitize_name(metadata["name"])
        if name in skills:
            raise SkillSyncError(f"duplicate skill name in registry source: {name}")
        skills[name] = {
            "version": str(metadata["version"]),
            "description": str(metadata.get("description", "")),
            "source": {"type": "local_path", "path": child.relative_to(root).as_posix()},
            "sha256": tree_sha256(child),
            "files": list_bundle_files(child),
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "source_root": str(root),
        "skills": skills,
    }


def registry_entry(registry: dict[str, Any], skill_name: str, registry_path: Path, source_root: Path | None) -> SkillEntry:
    if registry.get("schema_version") != SCHEMA_VERSION:
        raise SkillSyncError(f"unsupported registry schema_version: {registry.get('schema_version')!r}")
    skills = registry.get("skills")
    if not isinstance(skills, dict):
        raise SkillSyncError("registry must contain a skills object")
    raw = skills.get(skill_name)
    if not isinstance(raw, dict):
        raise SkillSyncError(f"skill not found in registry: {skill_name}")
    source = raw.get("source")
    if not isinstance(source, dict) or source.get("type") not in {"local_path", "file"}:
        raise SkillSyncError(f"skill {skill_name} must use source.type local_path or file")
    version = raw.get("version")
    expected_sha = raw.get("sha256")
    if not isinstance(version, str) or not isinstance(expected_sha, str):
        raise SkillSyncError(f"skill {skill_name} must include version and sha256")
    path_value = source.get("path")
    if not isinstance(path_value, str):
        raise SkillSyncError(f"skill {skill_name} source.path must be a string")
    description = raw.get("description") if isinstance(raw.get("description"), str) else ""
    registry_source_root = registry.get("source_root") if isinstance(registry.get("source_root"), str) else None
    base_dir = source_root or (Path(registry_source_root).resolve() if registry_source_root else registry_path.parent)
    return SkillEntry(
        name=sanitize_name(skill_name),
        version=version,
        source_path=resolve_source_path(path_value, base_dir, source_root),
        sha256_value=expected_sha,
        description=description,
    )


def installed_manifest(install_root: Path, skill_name: str) -> dict[str, Any] | None:
    manifest_path = install_root / skill_name / INSTALL_MANIFEST
    if not manifest_path.is_file():
        return None
    return load_json(manifest_path)


def copy_bundle(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for path in iter_regular_files(source):
        rel = path.relative_to(source)
        target = destination / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def install_or_update(
    entry: SkillEntry,
    install_root: Path,
    *,
    mode: str,
    allow_downgrade: bool = False,
) -> dict[str, Any]:
    actual_sha = tree_sha256(entry.source_path)
    if actual_sha != entry.sha256:
        raise SkillSyncError(f"registry hash mismatch for {entry.name}: expected {entry.sha256}, got {actual_sha}")

    install_root = install_root.resolve()
    install_root.mkdir(parents=True, exist_ok=True)
    current = installed_manifest(install_root, entry.name)
    if mode == "update" and current is None:
        raise SkillSyncError(f"cannot update missing skill: {entry.name}")

    action = "installed"
    if current is not None:
        current_version = str(current.get("version", ""))
        cmp = version_cmp(entry.version, current_version)
        if cmp == 0 and current.get("sha256") == entry.sha256:
            action = "noop"
        elif cmp < 0 and not allow_downgrade:
            raise SkillSyncError(f"refusing downgrade for {entry.name}: {current_version} -> {entry.version}")
        else:
            action = "updated"

    skill_dir = install_root / entry.name
    proof: dict[str, Any] = {
        "status": "completed",
        "action": action,
        "skill": entry.name,
        "version": entry.version,
        "sha256": entry.sha256,
        "source_path": str(entry.source_path),
        "install_path": str(skill_dir),
        "previous_manifest": current,
        "installed_at": utc_now(),
        "network_sources_allowed": False,
    }
    if action == "noop":
        proof["post_manifest"] = current
        return proof

    tmp_dir = Path(tempfile.mkdtemp(prefix=f".{entry.name}.", dir=install_root))
    rollback_dir: Path | None = None
    try:
        copy_bundle(entry.source_path, tmp_dir)
        manifest = {
            "name": entry.name,
            "version": entry.version,
            "description": entry.description,
            "sha256": entry.sha256,
            "source_path": str(entry.source_path),
            "installed_at": proof["installed_at"],
            "files": list_bundle_files(entry.source_path),
        }
        atomic_write_json(tmp_dir / INSTALL_MANIFEST, manifest)
        if skill_dir.exists():
            rollback_dir = install_root / f".{entry.name}.rollback.{int(datetime.now(timezone.utc).timestamp())}"
            os.replace(skill_dir, rollback_dir)
        os.replace(tmp_dir, skill_dir)
        if rollback_dir is not None:
            shutil.rmtree(rollback_dir)
        proof["post_manifest"] = manifest
        proof["installed_file_count"] = len(manifest["files"])
        return proof
    except Exception:
        if skill_dir.exists() and rollback_dir is not None and not rollback_dir.exists():
            shutil.rmtree(skill_dir, ignore_errors=True)
        if rollback_dir is not None and rollback_dir.exists() and not skill_dir.exists():
            os.replace(rollback_dir, skill_dir)
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise


def cmd_build_registry(args: argparse.Namespace) -> int:
    registry = build_registry(Path(args.source_root))
    if args.output:
        atomic_write_json(Path(args.output), registry)
    print_json(registry)
    return 0


def cmd_install_update(args: argparse.Namespace) -> int:
    registry_path = Path(args.registry).resolve()
    registry = load_json(registry_path)
    source_root = Path(args.source_root).resolve() if args.source_root else None
    entry = registry_entry(registry, args.skill, registry_path, source_root)
    proof = install_or_update(
        entry,
        Path(args.install_root),
        mode=args.command,
        allow_downgrade=args.allow_downgrade,
    )
    if args.proof:
        atomic_write_json(Path(args.proof), proof)
    print_json(proof)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    install_root = Path(args.install_root).resolve()
    if args.skill:
        print_json(installed_manifest(install_root, sanitize_name(args.skill)) or {"status": "missing", "skill": args.skill})
        return 0
    skills = {}
    if install_root.is_dir():
        for child in sorted(path for path in install_root.iterdir() if path.is_dir() and not path.name.startswith(".")):
            manifest = installed_manifest(install_root, child.name)
            if manifest is not None:
                skills[child.name] = manifest
    print_json({"status": "completed", "install_root": str(install_root), "skills": skills})
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build and apply Kolibri local skill registries")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build-registry")
    build.add_argument("--source-root", required=True, help="Directory containing one subdirectory per skill")
    build.add_argument("--output", help="Optional registry JSON path")
    build.set_defaults(func=cmd_build_registry)

    for command in ("install", "update"):
        install = sub.add_parser(command)
        install.add_argument("--registry", required=True)
        install.add_argument("--skill", required=True)
        install.add_argument("--install-root", required=True)
        install.add_argument("--source-root", help="Optional allowlist root for registry source paths")
        install.add_argument("--proof", help="Write artifact proof JSON")
        install.add_argument("--allow-downgrade", action="store_true")
        install.set_defaults(func=cmd_install_update)

    status = sub.add_parser("status")
    status.add_argument("--install-root", required=True)
    status.add_argument("--skill")
    status.set_defaults(func=cmd_status)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except SkillSyncError as exc:
        print_json({"status": "blocked", "blocked_reason": str(exc)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
