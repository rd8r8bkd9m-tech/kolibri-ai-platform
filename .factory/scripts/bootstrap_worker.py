#!/usr/bin/env python3
"""Bootstrap one remote Kolibri worker with official Mimocode and repo bundle."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from common import FACTORY, ROOT, load_json, write_json


AGENTS_FILE = ROOT / "ops" / "agents.yml"
BOOTSTRAP_LOG = FACTORY / "runs" / "worker_bootstrap.json"
INSTALL_URL = "https://mimo.xiaomi.com/install"


REMOTE_BOOTSTRAP = r"""
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
repo_bundle="$1"
repo_dir="$2"
worktree_root="$3"
mimo_bin="$4"

apt-get update -y
apt-get install -y git ca-certificates curl tar gzip
curl -fsSL https://mimo.xiaomi.com/install | bash -s -- --no-modify-path
mkdir -p "$repo_dir" "$worktree_root" /opt/kolibri-ai/reports
rm -rf "$repo_dir"
git clone "$repo_bundle" "$repo_dir"
"$mimo_bin" --version
"$mimo_bin" --help 2>&1 | grep -E 'mimo run|run mimocode|run \[message' >/dev/null
git -C "$repo_dir" rev-parse HEAD
"""


def run(argv: list[str], *, input_text: str | None = None, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        input=input_text,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def ssh_base(cfg: dict[str, Any]) -> list[str]:
    argv = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=30",
        "-o",
        "ConnectionAttempts=1",
        "-o",
        "ServerAliveInterval=10",
        "-o",
        "ServerAliveCountMax=2",
    ]
    if cfg.get("ssh_port"):
        argv.extend(["-p", str(cfg["ssh_port"])])
    argv.append(str(cfg["ssh_alias"]))
    return argv


def scp_base(cfg: dict[str, Any]) -> list[str]:
    argv = [
        "scp",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=30",
        "-o",
        "ConnectionAttempts=1",
    ]
    if cfg.get("ssh_port"):
        argv.extend(["-P", str(cfg["ssh_port"])])
    return argv


def load_server(server_id: str) -> dict[str, Any]:
    agents = load_json(AGENTS_FILE)
    cfg = agents.get("servers", {}).get(server_id)
    if not cfg:
        raise SystemExit(f"Unknown server: {server_id}")
    if not cfg.get("ssh_alias"):
        raise SystemExit(f"Server {server_id} has no ssh_alias")
    return cfg


def create_bundle(path: Path) -> str:
    proc = run(["git", "bundle", "create", str(path), "HEAD"], timeout=180)
    if proc.returncode != 0:
        raise SystemExit(proc.stderr or proc.stdout)
    return proc.stdout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()

    cfg = load_server(args.server)
    remote_repo = "/opt/kolibri-ai/repo"
    remote_bundle = f"/opt/kolibri-ai/{args.server}-factory.bundle"
    worktree_root = str(cfg.get("remote_worktree_root") or "/opt/kolibri-ai/agent-worktrees")
    mimo_bin = str(cfg.get("mimo_bin") or "/root/.mimocode/bin/mimo")
    if args.server == "main" and mimo_bin == "/usr/bin/mimo":
        return print_json({
            "ok": False,
            "server": args.server,
            "blocked": "main has a non-Mimocode /usr/bin/mimo; do not overwrite production gateway automatically"
        }, 2)

    plan = {
        "server": args.server,
        "ssh_alias": cfg["ssh_alias"],
        "install_url": INSTALL_URL,
        "remote_repo": remote_repo,
        "remote_bundle": remote_bundle,
        "worktree_root": worktree_root,
        "mimo_bin": mimo_bin,
    }
    if args.dry_run:
        return print_json({"ok": True, "dry_run": True, "plan": plan}, 0)

    with tempfile.TemporaryDirectory() as tmp:
        bundle = Path(tmp) / "kolibri-factory.bundle"
        create_bundle(bundle)

        mkdir = run(ssh_base(cfg) + ["mkdir -p /opt/kolibri-ai"], timeout=90)
        if mkdir.returncode != 0:
            return record(args.server, False, "ssh mkdir failed", mkdir, plan, 1)

        copy = run(scp_base(cfg) + [str(bundle), f"{cfg['ssh_alias']}:{remote_bundle}"], timeout=args.timeout)
        if copy.returncode != 0:
            return record(args.server, False, "bundle copy failed", copy, plan, 1)

        command = "bash -s -- " + " ".join(
            shlex.quote(value) for value in [remote_bundle, remote_repo, worktree_root, mimo_bin]
        )
        boot = run(ssh_base(cfg) + [command], input_text=REMOTE_BOOTSTRAP, timeout=args.timeout)
        if boot.returncode != 0:
            return record(args.server, False, "remote bootstrap failed", boot, plan, 1)
        return record(args.server, True, "worker bootstrapped", boot, plan, 0)


def record(server: str, ok: bool, summary: str, proc: subprocess.CompletedProcess[str], plan: dict[str, Any], code: int) -> int:
    existing = load_json(BOOTSTRAP_LOG) if BOOTSTRAP_LOG.exists() else {"runs": []}
    entry = {
        "server": server,
        "ok": ok,
        "summary": summary,
        "returncode": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-4000:],
        "stderr_tail": (proc.stderr or "")[-4000:],
        "plan": plan,
    }
    existing.setdefault("runs", []).append(entry)
    existing["runs"] = existing["runs"][-100:]
    write_json(BOOTSTRAP_LOG, existing)
    return print_json(entry, code)


def print_json(payload: dict[str, Any], code: int) -> int:
    print(json.dumps(payload, ensure_ascii=True, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
