#!/usr/bin/env python3
"""Launch bounded Kolibri agent tasks across multiple servers.

This is an operational wrapper around the safe worktree preparer and
`mimo_task_runner.py`. It deliberately does not talk to Mimo/OpenClaw itself;
the runner remains the only place that builds agent argv.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_LOG_DIR = PROJECT_DIR / "logs" / "agent-runs" / "fanout"
DEFAULT_MAX_WORKERS = 6


READONLY_MANIFESTS = {
    "uiap": "ops/tasks/mimo-18-readonly/mimo-18-readonly-uiap.json",
    "qjns": "ops/tasks/mimo-18-readonly/mimo-18-readonly-qjns.json",
    "9fts": "ops/tasks/mimo-18-readonly/mimo-18-readonly-9fts.json",
    "kolibri": "ops/tasks/mimo-18-readonly/mimo-18-readonly-kolibri.json",
    "reserve242": "ops/tasks/mimo-18-readonly/mimo-18-readonly-reserve242.json",
    "hostvds-highload": "ops/tasks/mimo-18-readonly/mimo-18-readonly-hostvds-highload.json",
    "hostvds-agent-01": "ops/tasks/mimo-18-readonly/mimo-18-readonly-hostvds-agent-01.json",
    "hostvds-agent-02": "ops/tasks/mimo-18-readonly/mimo-18-readonly-hostvds-agent-02.json",
    "hostvds-agent-03": "ops/tasks/mimo-18-readonly/mimo-18-readonly-hostvds-agent-03.json",
    "hostvds-agent-04": "ops/tasks/mimo-18-readonly/mimo-18-readonly-hostvds-agent-04.json",
    "hostvds-agent-05": "ops/tasks/mimo-18-readonly/mimo-18-readonly-hostvds-agent-05.json",
    "hostvds-agent-06": "ops/tasks/mimo-18-readonly/mimo-18-readonly-hostvds-agent-06.json",
    "hostvds-agent-07": "ops/tasks/mimo-18-readonly/mimo-18-readonly-hostvds-agent-07.json",
    "hostvds-agent-08": "ops/tasks/mimo-18-readonly/mimo-18-readonly-hostvds-agent-08.json",
    "hostvds-agent-09": "ops/tasks/mimo-18-readonly/mimo-18-readonly-hostvds-agent-09.json",
    "hostvds-agent-10": "ops/tasks/mimo-18-readonly/mimo-18-readonly-hostvds-agent-10.json",
    "hostvds-paris-highload": "ops/tasks/mimo-18-readonly/mimo-18-readonly-hostvds-paris-highload.json",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_command(argv: list[str], timeout: int) -> dict[str, Any]:
    started_at = utc_now()
    try:
        proc = subprocess.run(
            argv,
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "status": "completed" if proc.returncode == 0 else "failed",
            "returncode": proc.returncode,
            "stdout": proc.stdout[-12000:],
            "stderr": proc.stderr[-12000:],
            "started_at": started_at,
            "completed_at": utc_now(),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "status": "timeout",
            "stdout": (exc.stdout or "")[-12000:],
            "stderr": (exc.stderr or "")[-12000:],
            "started_at": started_at,
            "completed_at": utc_now(),
        }


def run_readonly_server(server: str, manifest: str, skip_prepare: bool, timeout: int) -> dict[str, Any]:
    result: dict[str, Any] = {
        "server": server,
        "manifest": manifest,
        "started_at": utc_now(),
        "steps": [],
    }
    if not skip_prepare:
        result["steps"].append(
            {
                "name": "prepare_worktree",
                **run_command(
                    [
                        sys.executable,
                        "scripts/prepare_mimo_worktrees.py",
                        "--no-dry-run",
                        "--force",
                        "--server",
                        server,
                    ],
                    timeout=timeout,
                ),
            }
        )
        if result["steps"][-1]["status"] != "completed":
            result["status"] = "failed"
            result["completed_at"] = utc_now()
            return result

    result["steps"].append(
        {
            "name": "run_agent",
            **run_command(
                [sys.executable, "scripts/mimo_task_runner.py", "run-ssh", "--manifest", manifest],
                timeout=timeout,
            ),
        }
    )
    result["status"] = result["steps"][-1]["status"]
    result["completed_at"] = utc_now()
    return result


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")


def run(args: argparse.Namespace) -> int:
    log_dir = Path(args.log_dir).expanduser().resolve()
    log_dir.mkdir(parents=True, exist_ok=True)
    run_id = args.run_id or f"fanout-{int(time.time())}"
    servers = args.server or list(READONLY_MANIFESTS)
    unknown = [server for server in servers if server not in READONLY_MANIFESTS]
    if unknown:
        raise SystemExit(f"Unknown read-only fanout server(s): {', '.join(unknown)}")

    summary: dict[str, Any] = {
        "run_id": run_id,
        "mode": "read_only_fanout",
        "servers": servers,
        "max_workers": args.max_workers,
        "started_at": utc_now(),
        "results": [],
    }
    summary_path = log_dir / f"{run_id}.json"
    write_json(summary_path, summary)

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = {
            executor.submit(
                run_readonly_server,
                server,
                READONLY_MANIFESTS[server],
                args.skip_prepare,
                args.timeout,
            ): server
            for server in servers
        }
        for future in concurrent.futures.as_completed(futures):
            item = future.result()
            summary["results"].append(item)
            write_json(log_dir / f"{run_id}-{item['server']}.json", item)
            write_json(summary_path, summary)
            print(json.dumps({"server": item["server"], "status": item["status"]}, ensure_ascii=True), flush=True)

    failures = [item for item in summary["results"] if item.get("status") != "completed"]
    summary["status"] = "failed" if failures else "completed"
    summary["completed_at"] = utc_now()
    write_json(summary_path, summary)
    return 1 if failures else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Launch parallel bounded agent fanout")
    parser.add_argument("--log-dir", default=str(DEFAULT_LOG_DIR))
    parser.add_argument("--run-id")
    parser.add_argument("--server", action="append", help="Server key; may be repeated. Defaults to all non-main VPS workers.")
    parser.add_argument("--max-workers", type=int, default=DEFAULT_MAX_WORKERS)
    parser.add_argument("--timeout", type=int, default=1200)
    parser.add_argument("--skip-prepare", action="store_true")
    return parser


def main() -> int:
    return run(build_parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
