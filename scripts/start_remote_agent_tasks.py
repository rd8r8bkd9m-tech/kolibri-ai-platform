#!/usr/bin/env python3
"""Start server-side detached Mimo tasks for the Kolibri agent fleet.

Mac/local Codex only dispatches payloads and records remote PIDs. The Mimo
process itself runs on each server and writes server-local result/log files.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import mimo_task_runner as runner


PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_LOG_DIR = PROJECT_DIR / "logs" / "agent-runs" / "remote-starts"
DEFAULT_REMOTE_RUN_ROOT = "/opt/kolibri-ai/agent-runs"


ROLE_OBJECTIVES = {
    "home": "FormulaLM Proof v1 preflight: verify dataset/run artifacts, logits environment gaps, service health, and next safe step. Do not start training.",
    "main": "Release node recovery: inspect disk pressure and service health, identify cleanup candidates and blockers. Do not delete files or restart services.",
    "uiap": "RAG/knowledge lane: review retrieval/index/API health and propose the next bounded RAG quality task.",
    "qjns": "Tools/agent executor lane: review worker completion and safe tool execution contracts.",
    "9fts": "Inference recovery lane: inspect inference target layout and blockers for canary serving.",
    "kolibri": "Worker lane: review background jobs, backup worker readiness, and safe queue execution gaps.",
    "reserve242": "QA/security lane: audit shell injection, secret redaction, and no-secrets test coverage.",
    "hostvds-highload": "Build/release lane: inspect build/test toolchain readiness and propose CI quality gate execution.",
    "hostvds-agent-01": "Backend lane: inspect RAG/API mismatch and Intent.AUTO routing, then return a controlled patch plan.",
    "hostvds-agent-02": "Frontend/design lane: inspect Agent Ops UI and browser QA gaps, then return a controlled patch plan.",
    "hostvds-agent-03": "Infra lane: inspect worker completion endpoint, VPN/systemd hardening, and deployment blockers.",
    "hostvds-agent-04": "Browser QA lane: design a desktop/mobile browser QA baseline and identify missing automation.",
    "hostvds-agent-05": "Security lane: audit orchestration permission boundaries, log redaction, and prompt handling.",
    "hostvds-agent-06": "Docs lane: inspect orchestration docs/runbooks and propose updates tied to actual hardening state.",
    "hostvds-agent-07": "FormulaLM eval lane: review Proof v1 metrics contract and evaluator requirements.",
    "hostvds-agent-08": "RAG eval lane: review retrieval baseline/eval fixtures and leakage risks.",
    "hostvds-agent-09": "Canary lane: inspect release smoke/rollback readiness and propose a safe canary checklist.",
    "hostvds-agent-10": "Asia edge/performance lane: inspect latency/load benchmark needs and OpenClaw frontend audit results.",
    "hostvds-paris-highload": "Reserve build lane: inspect build burst readiness and fallback CI capacity.",
}


REMOTE_DETACHED = r"""
import json
import os
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

payload_path = Path(sys.argv[1])
result_path = Path(sys.argv[2])
payload = json.loads(payload_path.read_text(encoding="utf-8"))
started_at = datetime.now(timezone.utc).isoformat()
worktree = Path(payload["worktree"])
worktree.mkdir(parents=True, exist_ok=True)

def text_tail(value):
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)

argv = [
    payload["agent_bin"],
    "run",
    "--format",
    "json",
    "--dir",
    str(worktree),
    "--model",
    payload["model"],
    payload["prompt"],
]

try:
    proc = subprocess.run(
        argv,
        cwd=str(worktree),
        capture_output=True,
        text=True,
        timeout=payload["timeout_seconds"],
        check=False,
    )
    status = "completed" if proc.returncode == 0 else "failed"
    summary_source = (proc.stdout or proc.stderr or "").strip().splitlines()
    summary = next((line.strip() for line in summary_source if line.strip()), "No output")[:240]
    result = {
        "task_id": payload["task_id"],
        "server": payload["server"],
        "status": status,
        "summary": summary,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "changed_files": [],
        "checks": [],
        "risks": [],
        "artifacts": [],
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
except subprocess.TimeoutExpired as exc:
    result = {
        "task_id": payload["task_id"],
        "server": payload["server"],
        "status": "timeout",
        "summary": "Mimo task timed out",
        "stdout": text_tail(exc.stdout),
        "stderr": text_tail(exc.stderr),
        "changed_files": [],
        "checks": [],
        "risks": ["timeout"],
        "artifacts": [],
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
except FileNotFoundError:
    result = {
        "task_id": payload["task_id"],
        "server": payload["server"],
        "status": "failed",
        "summary": "Mimo binary not found",
        "stdout": "",
        "stderr": "Mimo binary not found: " + payload["agent_bin"],
        "changed_files": [],
        "checks": [],
        "risks": ["agent_binary_not_found"],
        "artifacts": [],
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }

result_path.write_text(json.dumps(result, ensure_ascii=True, indent=2), encoding="utf-8")
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def task_prompt(server: str, config: dict[str, Any]) -> str:
    objective = ROLE_OBJECTIVES.get(server, f"Inspect the {config.get('role', 'agent')} lane and propose the next bounded task.")
    allowed = "\n".join(f"- {item}" for item in config.get("allowed_paths", []))
    return (
        f"{objective}\n\n"
        "Run on this server only. Inspect only allowed paths and public service metadata.\n"
        "Do not mutate files unless the task is explicitly a controlled mutation; this launch is read-only/discovery.\n"
        "Do not read .env, auth files, private keys, tokens, passwords, .ssh, or .mimocode.\n"
        "Return a concrete development task for the next agent cycle, with exact files, checks, blockers, and risks.\n\n"
        f"Allowed server paths:\n{allowed}"
    )


def build_manifest(server: str, config: dict[str, Any], run_id: str, timeout: int) -> dict[str, Any]:
    worktree_root = str(config.get("remote_worktree_root") or "/opt/kolibri-ai/agent-worktrees").rstrip("/")
    worktree = "/srv/kolibri/repo" if server == "home" else f"{worktree_root}/server-discovery-{run_id}-{server}"
    prompt = task_prompt(server, config)
    return {
        "task_id": f"server-discovery-{server}",
        "agent_role": config.get("deputy") or config.get("role") or "Server Agent",
        "agent_backend": "mimo",
        "server": server,
        "mode": "read_only",
        "prompt": prompt,
        "worktree": worktree,
        "allowed_paths": [worktree, *list(config.get("allowed_paths") or [])],
        "quality_contract": runner.default_quality_contract(prompt, str(config.get("role") or "server-discovery"), "read_only"),
        "required_checks": [],
        "timeout_seconds": timeout,
        "secrets_policy": {
            "allow_env_files": False,
            "allow_auth_files": False,
            "redact_logs": True,
        },
        "expected_output": {
            "format": "structured_result",
            "requires_summary": True,
            "requires_changed_files": True,
            "requires_risks": True,
        },
        "allow_unsafe_permissions": False,
    }


def ssh_base(config: dict[str, Any]) -> list[str]:
    cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15"]
    if config.get("ssh_port"):
        cmd.extend(["-p", str(config["ssh_port"])])
    cmd.append(str(config["ssh_alias"]))
    return cmd


def start_one(server: str, config: dict[str, Any], run_id: str, timeout: int, remote_root: str) -> dict[str, Any]:
    manifest = build_manifest(server, config, run_id, timeout)
    errors = runner.validate_manifest(manifest, {"servers": {server: config}})
    if errors:
        return {"server": server, "status": "failed", "errors": errors}
    runner.ensure_no_secret_prompt(manifest["prompt"])
    prompt = runner.prompt_for_agent(manifest)
    runner.ensure_no_secret_prompt(prompt)

    remote_dir = f"{remote_root.rstrip('/')}/{run_id}/{server}"
    payload = {
        "task_id": manifest["task_id"],
        "server": server,
        "agent_bin": config.get("mimo_bin") or "mimo",
        "worktree": manifest["worktree"],
        "model": manifest.get("model", runner.DEFAULT_MODEL),
        "prompt": prompt,
        "timeout_seconds": manifest["timeout_seconds"],
    }

    mkdir_cmd = ssh_base(config) + [f"mkdir -p {shlex.quote(remote_dir)} && cat > {shlex.quote(remote_dir + '/payload.json')}"]
    proc = subprocess.run(mkdir_cmd, input=json.dumps(payload), text=True, capture_output=True, timeout=45, check=False)
    if proc.returncode != 0:
        return {
            "server": server,
            "status": "failed",
            "summary": "payload upload failed",
            "stdout": proc.stdout[-2000:],
            "stderr": proc.stderr[-2000:],
        }

    payload_path = shlex.quote(remote_dir + "/payload.json")
    result_path = shlex.quote(remote_dir + "/result.json")
    runner_path = shlex.quote(remote_dir + "/runner.py")
    stdout_path = shlex.quote(remote_dir + "/stdout.log")
    stderr_path = shlex.quote(remote_dir + "/stderr.log")
    runner_upload = ssh_base(config) + [f"cat > {runner_path}"]
    upload = subprocess.run(runner_upload, input=REMOTE_DETACHED, text=True, capture_output=True, timeout=45, check=False)
    if upload.returncode != 0:
        return {
            "server": server,
            "status": "failed",
            "summary": "runner upload failed",
            "stdout": upload.stdout[-2000:],
            "stderr": upload.stderr[-2000:],
            "remote_dir": remote_dir,
        }
    start_cmd = (
        f"cd {shlex.quote(remote_dir)} && "
        f"(setsid python3 {runner_path} {payload_path} {result_path} "
        f"> {stdout_path} 2> {stderr_path} < /dev/null & echo $!)"
    )
    start = subprocess.run(ssh_base(config) + [start_cmd], capture_output=True, text=True, timeout=45, check=False)
    if start.returncode != 0:
        return {
            "server": server,
            "status": "failed",
            "summary": "remote start failed",
            "stdout": start.stdout[-2000:],
            "stderr": start.stderr[-2000:],
            "remote_dir": remote_dir,
        }
    return {
        "server": server,
        "status": "started",
        "pid": start.stdout.strip().splitlines()[-1] if start.stdout.strip() else "",
        "remote_dir": remote_dir,
        "result_path": remote_dir + "/result.json",
        "stdout_path": remote_dir + "/stdout.log",
        "stderr_path": remote_dir + "/stderr.log",
        "worktree": manifest["worktree"],
        "started_at": utc_now(),
    }


def run(args: argparse.Namespace) -> int:
    agents = runner.load_agents(Path(args.agents_file).expanduser().resolve())
    servers = args.server or [name for name, cfg in agents.get("servers", {}).items() if cfg.get("enabled", True)]
    run_id = args.run_id or f"remote-agents-{int(time.time())}"

    def dispatch(server: str) -> dict[str, Any]:
        try:
            config = runner.server_config(agents, server)
            if not config.get("ssh_alias"):
                return {"server": server, "status": "failed", "summary": "missing ssh_alias"}
            return start_one(server, config, run_id, args.timeout, args.remote_root)
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout if isinstance(exc.stdout, str) else ""
            stderr = exc.stderr if isinstance(exc.stderr, str) else ""
            return {
                "server": server,
                "status": "failed",
                "summary": "ssh dispatch timed out",
                "stdout": stdout[-2000:],
                "stderr": stderr[-2000:],
            }
        except Exception as exc:
            return {"server": server, "status": "failed", "summary": str(exc)}

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = {executor.submit(dispatch, server): server for server in servers}
        for future in concurrent.futures.as_completed(futures):
            item = future.result()
            results.append(item)
            print(json.dumps({"server": item.get("server"), "status": item.get("status")}, ensure_ascii=True), flush=True)

    summary = {
        "run_id": run_id,
        "mode": "server_side_detached_mimo",
        "started_at": utc_now(),
        "results": results,
    }
    log_dir = Path(args.log_dir).expanduser().resolve()
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"{run_id}.json"
    path.write_text(json.dumps(summary, ensure_ascii=True, indent=2), encoding="utf-8")
    print(json.dumps({"log": str(path), **summary}, ensure_ascii=True, indent=2))
    return 0 if all(item.get("status") == "started" for item in results) else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Start detached server-side Mimo tasks")
    parser.add_argument("--agents-file", default=str(runner.DEFAULT_AGENTS_FILE))
    parser.add_argument("--log-dir", default=str(DEFAULT_LOG_DIR))
    parser.add_argument("--run-id")
    parser.add_argument("--server", action="append")
    parser.add_argument("--max-workers", type=int, default=8)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--remote-root", default=DEFAULT_REMOTE_RUN_ROOT)
    return parser


def main() -> int:
    return run(build_parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
