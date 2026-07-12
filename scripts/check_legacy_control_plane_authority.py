#!/usr/bin/env python3
"""Fail when executable Kolibri runtime embeds a legacy Control Plane.

The gate deliberately scans product runtime sources and release manifests, not
historical documentation or test fixtures.  It is read-only, does not follow
symlinks, and skips secret-bearing file types and generated dependency trees.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import namedtuple
from pathlib import Path
from typing import Any, Iterable


RUNTIME_ROOTS = (
    "backend",
    "frontend/src",
    "ops",
    "scripts",
    "deploy",
    "services",
    "crates",
    "apps",
    "configs",
)
RUNTIME_SUFFIXES = {
    ".c",
    ".h",
    ".js",
    ".json",
    ".jsx",
    ".mjs",
    ".py",
    ".rs",
    ".service",
    ".sh",
    ".socket",
    ".toml",
    ".ts",
    ".tsx",
    ".yaml",
    ".yml",
}
MANIFEST_SUFFIXES = {".json", ".toml", ".yaml", ".yml"}
GENERATED_PARTS = {
    ".cache",
    ".factory",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "artifacts",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "target",
    "tmp",
    "venv",
}
TEST_PARTS = {"test", "tests", "fixtures", "snapshots"}
SECRET_SUFFIXES = {".age", ".der", ".env", ".key", ".p12", ".pem"}
SECRET_FILE_MARKERS = ("credential", "private-key", "private_key", "secret")

_MAIN = "ma" + "in"
_PRIMARY = "pri" + "mary"
_PRIMARY_CANDIDATE = _PRIMARY + "-candidate"
_KOLIBRI_MAIN = "kolibri-" + _MAIN
_KOLIBRI_PRIMARY = "kolibri-" + _PRIMARY
_LEGACY_IP = "10.99.0." + "2"
_CONTROL_PLANE_SOURCE = "control-plane/"

LEGACY_CONTROL_PLANE_URL = re.compile(
    rf"(?i)https?://(?:{re.escape(_LEGACY_IP)}|"
    rf"{re.escape(_KOLIBRI_MAIN)}(?:-api)?|"
    rf"{re.escape(_KOLIBRI_PRIMARY)}(?:-codex)?|"
    rf"{re.escape(_PRIMARY_CANDIDATE)}):9101(?:/|\b)"
)
LEGACY_CONTROL_PLANE_SOURCE = re.compile(
    rf"(?i)(?<![a-z0-9_-]){re.escape(_CONTROL_PLANE_SOURCE)}(?:"
    rf"{re.escape(_MAIN)}|{re.escape(_PRIMARY)}|{re.escape(_PRIMARY_CANDIDATE)})"
    r"(?![a-z0-9_-])"
)
LEGACY_NODE_ALIAS = re.compile(
    rf"(?i)(?<![a-z0-9_-])(?:{re.escape(_PRIMARY_CANDIDATE)}|"
    rf"{re.escape(_KOLIBRI_MAIN)}(?:-api)?|"
    rf"{re.escape(_KOLIBRI_PRIMARY)}(?:-codex)?)(?![a-z0-9_-])"
)
STATIC_CONTROL_PLANE_LIST = re.compile(
    r"(?i)KOLIBRI_(?:FACTORY_)?CONTROL_URLS?\s*=\s*['\"][^'\"\n]*,"
    r"[^'\"\n]*['\"]"
)
SENSITIVE_IDENTITY_ASSIGNMENT = re.compile(
    r"(?i)(?:control[_-]?(?:plane|node|host|authority|url)|authority|"
    r"scheduler|leader|target_node|fallback_nodes?)\s*[:=]\s*"
    r"(?:\[[^\]\n]*|)['\"](?:main|primary)['\"]"
)
CONTROL_ROLE_RECORD = re.compile(
    r"(?i)(?:node_id|hostname)\s*[:=]\s*['\"](?:main|primary)['\"]"
    r"[^\n]{0,240}(?:role|capabilities)\s*[:=][^\n]{0,120}control(?:_plane)?"
)

SENSITIVE_MANIFEST_KEYS = {
    "authority",
    "authority_id",
    "authority_node",
    "command_node",
    "control_node",
    "control_plane",
    "control_plane_id",
    "control_plane_node",
    "control_plane_url",
    "control_url",
    "control_urls",
    "fallback_node",
    "fallback_nodes",
    "leader",
    "leader_node",
    "scheduler",
    "scheduler_node",
    "target_node",
}
GENERIC_LEGACY_IDENTITIES = {_MAIN, _PRIMARY, _PRIMARY_CANDIDATE}

# A Rust unit test deliberately corrupts the canonical source to prove that
# the verifier rejects it.  This exact fixture is allowed; arbitrary uses of
# the same legacy source remain violations.
INLINE_NEGATIVE_FIXTURES = {
    (
        "crates/kolibri-core/src/event_store.rs",
        'original.replace("control-plane/home", "'
        + _CONTROL_PLANE_SOURCE
        + _MAIN
        + '")',
    ),
}


Violation = namedtuple("Violation", ("path", "line", "rule", "token"))


def _relative_posix(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _is_secret_bearing(path: Path) -> bool:
    name = path.name.lower()
    return (
        name.startswith(".env")
        or path.suffix.lower() in SECRET_SUFFIXES
        or any(marker in name for marker in SECRET_FILE_MARKERS)
    )


def _is_runtime_source(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    if GENERATED_PARTS.intersection(relative.parts):
        return False
    if TEST_PARTS.intersection(part.lower() for part in relative.parts):
        return False
    if _is_secret_bearing(path) or path.is_symlink() or not path.is_file():
        return False
    if path.suffix.lower() in RUNTIME_SUFFIXES:
        return True
    return path.parent.name in {"ops", "scripts", "deploy"} and "." not in path.name


def _is_release_manifest(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    if GENERATED_PARTS.intersection(relative.parts):
        return False
    if _is_secret_bearing(path) or path.is_symlink() or not path.is_file():
        return False
    if path.suffix.lower() not in MANIFEST_SUFFIXES:
        return False
    name = path.name.lower()
    parts = {part.lower() for part in relative.parts}
    if "evidence" in parts:
        return False
    return (
        ("release" in parts or "releases" in parts) and "manifest" in name
    ) or name.startswith("release-policy.")


def candidate_files(root: Path) -> list[Path]:
    """Return deterministic in-repository candidates without following links."""

    candidates: dict[str, Path] = {}
    for relative_root in RUNTIME_ROOTS:
        runtime_root = root / relative_root
        if not runtime_root.is_dir() or runtime_root.is_symlink():
            continue
        for path in runtime_root.rglob("*"):
            if _is_runtime_source(path, root) or _is_release_manifest(path, root):
                candidates[_relative_posix(path, root)] = path

    release_root = root / "release"
    if release_root.is_dir() and not release_root.is_symlink():
        for path in release_root.rglob("*"):
            if _is_release_manifest(path, root):
                candidates[_relative_posix(path, root)] = path

    for pattern in ("docker-compose*.yml", "docker-compose*.yaml", "compose*.yml", "compose*.yaml"):
        for path in root.glob(pattern):
            if _is_runtime_source(path, root):
                candidates[_relative_posix(path, root)] = path
    return [candidates[key] for key in sorted(candidates)]


def _is_inline_negative_fixture(relative: str, line: str) -> bool:
    return any(
        relative == fixture_path and fixture_source in line
        for fixture_path, fixture_source in INLINE_NEGATIVE_FIXTURES
    )


def _line_for_token(source: str, token: str) -> int:
    folded_token = token.casefold()
    for number, line in enumerate(source.splitlines(), start=1):
        if folded_token in line.casefold():
            return number
    return 1


def _scan_text(path: Path, root: Path, source: str) -> list[Violation]:
    relative = _relative_posix(path, root)
    violations: list[Violation] = []
    rules = (
        ("legacy_control_plane_url", "legacy_endpoint", LEGACY_CONTROL_PLANE_URL),
        ("legacy_control_plane_source", "legacy_source", LEGACY_CONTROL_PLANE_SOURCE),
        ("legacy_control_plane_alias", "legacy_alias", LEGACY_NODE_ALIAS),
        ("multiple_control_plane_urls", "multiple_authorities", STATIC_CONTROL_PLANE_LIST),
        ("legacy_control_plane_identity", "legacy_identity", SENSITIVE_IDENTITY_ASSIGNMENT),
        ("legacy_control_plane_role", "legacy_control_role", CONTROL_ROLE_RECORD),
    )
    for number, line in enumerate(source.splitlines(), start=1):
        if _is_inline_negative_fixture(relative, line):
            continue
        for rule, safe_token, pattern in rules:
            match = pattern.search(line)
            if match:
                violations.append(Violation(relative, number, rule, safe_token))
                break
    return violations


def _normalized_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def _manifest_violations(
    value: Any,
    *,
    path: Path,
    root: Path,
    source: str,
    key: str = "",
    pointer: str = "$",
) -> Iterable[Violation]:
    relative = _relative_posix(path, root)
    if isinstance(value, dict):
        role = _normalized_key(value.get("role", ""))
        if role in {"control", "control_plane", "scheduler", "leader"}:
            for identity_key in ("node_id", "hostname", "id", "name"):
                identity = str(value.get(identity_key, "")).strip().lower()
                if identity in GENERIC_LEGACY_IDENTITIES or LEGACY_NODE_ALIAS.search(identity):
                    yield Violation(
                        relative,
                        _line_for_token(source, identity),
                        "release_manifest_legacy_control_plane_role",
                        "legacy_control_role",
                    )
        for child_key, child in value.items():
            yield from _manifest_violations(
                child,
                path=path,
                root=root,
                source=source,
                key=_normalized_key(child_key),
                pointer=f"{pointer}.{child_key}",
            )
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            yield from _manifest_violations(
                child,
                path=path,
                root=root,
                source=source,
                key=key,
                pointer=f"{pointer}[{index}]",
            )
        return
    if not isinstance(value, str):
        return

    normalized = value.strip().lower()
    match = LEGACY_CONTROL_PLANE_URL.search(value) or LEGACY_NODE_ALIAS.search(value)
    if match:
        yield Violation(
            relative,
            _line_for_token(source, match.group(0)),
            "release_manifest_legacy_control_plane_reference",
            "legacy_reference",
        )
    elif key in SENSITIVE_MANIFEST_KEYS and normalized in GENERIC_LEGACY_IDENTITIES:
        yield Violation(
            relative,
            _line_for_token(source, value),
            "release_manifest_legacy_control_plane_identity",
            "legacy_identity",
        )


def scan_repository(root: str | Path) -> list[Violation]:
    repository = Path(root).resolve()
    violations: list[Violation] = []
    for path in candidate_files(repository):
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            violations.append(
                Violation(
                    _relative_posix(path, repository),
                    1,
                    "runtime_source_unreadable",
                    type(exc).__name__,
                )
            )
            continue
        violations.extend(_scan_text(path, repository, source))
        if _is_release_manifest(path, repository) and path.suffix.lower() == ".json":
            try:
                payload = json.loads(source)
            except json.JSONDecodeError as exc:
                violations.append(
                    Violation(
                        _relative_posix(path, repository),
                        exc.lineno,
                        "release_manifest_invalid_json",
                        "invalid_json",
                    )
                )
            else:
                violations.extend(
                    _manifest_violations(
                        payload,
                        path=path,
                        root=repository,
                        source=source,
                    )
                )
    return sorted(set(violations))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root (defaults to the parent of scripts/)",
    )
    args = parser.parse_args(argv)
    violations = scan_repository(args.root)
    if violations:
        for violation in violations:
            print(
                f"{violation.path}:{violation.line}: {violation.rule}: {violation.token}"
            )
        print(f"legacy_control_plane_gate=failed violations={len(violations)}")
        return 1
    print(
        "legacy_control_plane_gate=ok "
        f"scanned_files={len(candidate_files(args.root.resolve()))}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
