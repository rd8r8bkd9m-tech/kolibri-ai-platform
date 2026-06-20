#!/usr/bin/env python3
"""Prepare read-only remote worktrees for Kolibri Mimo experiments.

This helper only prepares sanitized worktree snapshots. It does not invoke
Mimo, start agents, install packages, deploy services, or read credentials.
The transport is a gzip tar stream over SSH stdin so remote hosts do not need
rsync installed.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import shlex
import stat
import subprocess
import sys
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO


PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_AGENTS_FILE = PROJECT_DIR / "ops" / "agents.yml"
DEFAULT_LOG_DIR = PROJECT_DIR / "logs" / "agent-runs" / "worktree-prep"
DEFAULT_EXPERIMENT = "mimo-18-readonly"
DEFAULT_EXCLUDES = (
    ".agents",
    ".codex",
    ".git",
    ".mimocode",
    ".playwright-mcp",
    ".tmp",
    "node_modules",
    "target",
    "dist",
    "logs",
    ".env*",
    "*.pem",
    "*.key",
    "__pycache__",
    ".pytest_cache",
)
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")


class PrepError(RuntimeError):
    """User-facing preparation failure."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_agents(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        try:
            import yaml  # type: ignore
        except Exception as exc:
            raise PrepError(
                f"{path} is not JSON and PyYAML is not installed; keep agents.yml JSON-compatible"
            ) from exc
        data = yaml.safe_load(text)
        if not isinstance(data, dict):
            raise PrepError(f"{path} must contain a mapping")
        return data


def normalize_id(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
    if not safe or not SAFE_ID_RE.fullmatch(safe):
        raise PrepError(f"Unsafe identifier: {value!r}")
    return safe


def path_is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def posix_is_within(path: PurePosixPath, parent: PurePosixPath) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def excluded(relative: PurePosixPath, patterns: tuple[str, ...]) -> bool:
    parts = relative.parts
    text = relative.as_posix()
    for pattern in patterns:
        if fnmatch.fnmatch(relative.name, pattern) or fnmatch.fnmatch(text, pattern):
            return True
        if any(fnmatch.fnmatch(part, pattern) for part in parts):
            return True
    return False


def iter_archive_paths(source: Path, excludes: tuple[str, ...]) -> list[Path]:
    result: list[Path] = []
    for root, dirs, files in os.walk(source):
        root_path = Path(root)
        rel_root = PurePosixPath(root_path.relative_to(source).as_posix())
        if str(rel_root) == ".":
            rel_root = PurePosixPath("")
        kept_dirs = []
        for dirname in dirs:
            rel = rel_root / dirname
            if not excluded(rel, excludes):
                kept_dirs.append(dirname)
        dirs[:] = kept_dirs
        for filename in files:
            rel = rel_root / filename
            if excluded(rel, excludes):
                continue
            path = root_path / filename
            if path.is_symlink():
                continue
            result.append(path)
    return result


def safe_tarinfo(tar: tarfile.TarFile, path: Path, source: Path) -> tarfile.TarInfo | None:
    rel = PurePosixPath(path.relative_to(source).as_posix())
    if rel.is_absolute() or ".." in rel.parts:
        raise PrepError(f"Refusing unsafe archive path: {rel}")
    info = tar.gettarinfo(str(path), arcname=rel.as_posix())
    if not info.isfile():
        return None
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mode = stat.S_IMODE(info.mode) & 0o555
    return info


def write_archive(stream: BinaryIO, source: Path, excludes: tuple[str, ...]) -> tuple[int, int]:
    files = iter_archive_paths(source, excludes)
    with tarfile.open(fileobj=stream, mode="w|gz") as tar:
        for path in files:
            info = safe_tarinfo(tar, path, source)
            if info is None:
                continue
            with path.open("rb") as handle:
                tar.addfile(info, handle)
    total_bytes = sum(path.stat().st_size for path in files)
    return len(files), total_bytes


REMOTE_PREPARE = r"""
import json
import os
import stat
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


class RemotePrepError(Exception):
    pass


def posix_is_within(path, parent):
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def validate_member(member):
    rel = PurePosixPath(member.name)
    if rel.is_absolute() or ".." in rel.parts:
        raise RemotePrepError("unsafe archive path: " + member.name)
    if member.issym() or member.islnk() or member.isdev():
        raise RemotePrepError("unsafe archive member type: " + member.name)


def chmod_readonly(root):
    for current, dirs, files in os.walk(root):
        for dirname in dirs:
            os.chmod(Path(current) / dirname, 0o555)
        for filename in files:
            os.chmod(Path(current) / filename, 0o444)
    os.chmod(root, 0o555)


payload = json.loads(sys.stdin.buffer.readline().decode("utf-8"))
started_at = datetime.now(timezone.utc).isoformat()
root = Path(payload["remote_root"]).expanduser().resolve()
worktree = Path(payload["worktree"]).expanduser().resolve()
if not posix_is_within(worktree, root):
    raise RemotePrepError("worktree must be inside remote_root")
if worktree.exists() and any(worktree.iterdir()) and not payload.get("force"):
    raise RemotePrepError("worktree already exists and is not empty")

root.mkdir(parents=True, exist_ok=True)
worktree.mkdir(parents=True, exist_ok=True)
extracted = 0
with tarfile.open(fileobj=sys.stdin.buffer, mode="r|gz") as tar:
    for member in tar:
        validate_member(member)
        target = (worktree / member.name).resolve()
        if not posix_is_within(target, worktree):
            raise RemotePrepError("archive extraction escaped worktree: " + member.name)
        tar.extract(member, path=worktree, set_attrs=False)
        extracted += 1
chmod_readonly(worktree)
print(json.dumps({
    "status": "prepared",
    "server": payload["server"],
    "worktree": str(worktree),
    "files": extracted,
    "read_only": True,
    "started_at": started_at,
    "completed_at": datetime.now(timezone.utc).isoformat(),
}))
"""


def enabled_servers(agents: dict[str, Any], include_home: bool) -> list[str]:
    servers = []
    for name, config in agents.get("servers", {}).items():
        if not config.get("enabled", True):
            continue
        if name == "home" and not include_home:
            continue
        servers.append(name)
    return servers


def selected_servers(args: argparse.Namespace, agents: dict[str, Any]) -> list[str]:
    available = enabled_servers(agents, args.include_home)
    if args.server:
        requested = [normalize_id(item) for item in args.server]
        missing = [item for item in requested if item not in available]
        if missing:
            raise PrepError(f"Requested server is not enabled or allowed: {', '.join(missing)}")
        return requested
    return available


def remote_worktree_for(config: dict[str, Any], server: str, experiment: str) -> str:
    remote_root = config.get("remote_worktree_root")
    if not isinstance(remote_root, str) or not remote_root.startswith("/"):
        raise PrepError(f"Server has no absolute remote_worktree_root: {server}")
    return f"{remote_root.rstrip('/')}/{normalize_id(experiment)}-{normalize_id(server)}"


def write_log(log_dir: Path, payload: dict[str, Any]) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    server = normalize_id(str(payload.get("server", "summary")))
    path = log_dir / f"{server}-{int(time.time())}.json"
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    return path


def prepare_one(
    server: str,
    config: dict[str, Any],
    source: Path,
    experiment: str,
    excludes: tuple[str, ...],
    args: argparse.Namespace,
) -> dict[str, Any]:
    remote_root = str(config["remote_worktree_root"]).rstrip("/")
    worktree = remote_worktree_for(config, server, experiment)
    manifest = {
        "server": server,
        "ssh_alias": config.get("ssh_alias"),
        "remote_root": remote_root,
        "worktree": worktree,
        "experiment": experiment,
        "excludes": list(excludes),
    }

    files = iter_archive_paths(source, excludes)
    if args.dry_run:
        return {
            **manifest,
            "status": "dry_run",
            "files": len(files),
            "bytes": sum(path.stat().st_size for path in files),
            "read_only": True,
            "summary": "No SSH connection opened and no remote files changed.",
        }

    ssh_alias = config.get("ssh_alias")
    if not isinstance(ssh_alias, str) or not ssh_alias:
        raise PrepError(f"Server has no ssh_alias: {server}")

    ssh_cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]
    if config.get("ssh_port"):
        ssh_cmd.extend(["-p", str(config["ssh_port"])])
    ssh_cmd.extend([ssh_alias, "python3 -c " + shlex.quote(REMOTE_PREPARE)])
    payload = {
        "server": server,
        "remote_root": remote_root,
        "worktree": worktree,
        "force": bool(args.force),
    }
    started_at = utc_now()
    proc = subprocess.Popen(
        ssh_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=False,
    )
    assert proc.stdin is not None
    proc.stdin.write(json.dumps(payload).encode("utf-8") + b"\n")
    file_count = 0
    byte_count = 0
    try:
        file_count, byte_count = write_archive(proc.stdin, source, excludes)
        proc.stdin.close()
        proc.stdin = None
        stdout, stderr = proc.communicate(timeout=args.timeout)
    except (BrokenPipeError, OSError) as exc:
        if proc.stdin is not None:
            try:
                proc.stdin.close()
            except OSError:
                pass
            proc.stdin = None
        stdout, stderr = proc.communicate(timeout=args.timeout)
        return {
            **manifest,
            "status": "failed",
            "returncode": proc.returncode,
            "stdout": stdout.decode("utf-8", "replace")[-4000:],
            "stderr": stderr.decode("utf-8", "replace")[-4000:],
            "files": file_count,
            "bytes": byte_count,
            "risks": ["ssh_prepare_failed", "archive_stream_failed"],
            "error": str(exc),
            "started_at": started_at,
            "completed_at": utc_now(),
        }
    if proc.returncode != 0:
        return {
            **manifest,
            "status": "failed",
            "returncode": proc.returncode,
            "stdout": stdout.decode("utf-8", "replace")[-4000:],
            "stderr": stderr.decode("utf-8", "replace")[-4000:],
            "files": file_count,
            "bytes": byte_count,
            "risks": ["ssh_prepare_failed"],
            "started_at": started_at,
            "completed_at": utc_now(),
        }
    try:
        result = json.loads(stdout.decode("utf-8"))
    except json.JSONDecodeError:
        result = {
            "status": "failed",
            "summary": "Remote prepare returned non-JSON output",
            "stdout": stdout.decode("utf-8", "replace")[-4000:],
            "stderr": stderr.decode("utf-8", "replace")[-4000:],
            "risks": ["invalid_remote_output"],
        }
    result.update({"bytes": byte_count, "source_files": file_count})
    return {**manifest, **result}


def run(args: argparse.Namespace) -> int:
    source = Path(args.source).expanduser().resolve()
    if not path_is_within(source, PROJECT_DIR):
        raise PrepError(f"Source must be inside project: {source}")
    if not source.exists() or not source.is_dir():
        raise PrepError(f"Source directory not found: {source}")

    experiment = normalize_id(args.experiment)
    agents = load_agents(Path(args.agents_file).expanduser().resolve())
    servers = selected_servers(args, agents)
    excludes = tuple(dict.fromkeys([*DEFAULT_EXCLUDES, *(args.exclude or [])]))
    results = []
    for server in servers:
        config = agents["servers"][server]
        result = prepare_one(server, config, source, experiment, excludes, args)
        result["log"] = str(write_log(Path(args.log_dir).expanduser().resolve(), result))
        results.append(result)

    failures = [item for item in results if item.get("status") not in {"dry_run", "prepared"}]
    print(json.dumps({"status": "failed" if failures else "ok", "count": len(results), "results": results}, indent=2))
    return 1 if failures else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare read-only Mimo experiment worktrees over SSH tar streams")
    parser.add_argument("--agents-file", default=str(DEFAULT_AGENTS_FILE))
    parser.add_argument("--log-dir", default=str(DEFAULT_LOG_DIR))
    parser.add_argument("--source", default=str(PROJECT_DIR))
    parser.add_argument("--experiment", default=DEFAULT_EXPERIMENT)
    parser.add_argument("--server", action="append", help="Enabled server key; may be repeated. Defaults to all enabled non-home servers.")
    parser.add_argument("--include-home", action="store_true", help="Include home; disabled by default for the 18-VPS experiment.")
    parser.add_argument("--exclude", action="append", help="Additional exclude pattern; repeat for each pattern.")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--force", action="store_true", help="Allow preparing into an existing non-empty worktree.")
    parser.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return run(args)
    except subprocess.TimeoutExpired as exc:
        print(f"ERROR: SSH preparation timed out: {exc}", file=sys.stderr)
        return 2
    except PrepError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
