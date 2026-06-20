#!/usr/bin/env python3
"""Kolibri agent factory control-plane.

The factory is intentionally small and boring:
- keeps a local queue/state file;
- dispatches detached Mimo tasks to remote servers;
- returns immediately after dispatch;
- collects result.json files later;
- prints a Codex review report without merging or deploying anything.

Mimo/OpenClaw workers execute bounded tasks. Codex remains the reviewer.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import shlex
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parents[1]
STATE_DIR = PROJECT_DIR / "logs" / "agent-factory"
LEGACY_STATE_FILE = STATE_DIR / "state.json"
FACTORY_STATE_DIR = PROJECT_DIR / ".factory" / "runs"
STATE_FILE = FACTORY_STATE_DIR / "agent_factory_state.json"
AGENTS_FILE = PROJECT_DIR / "ops" / "agents.yml"
DEFAULT_REMOTE_ROOT = "/opt/kolibri-ai/agent-runs"
HOME_REMOTE_ROOT = "/home/ladik/agent-runs"
DEFAULT_TIMEOUT_SECONDS = 900


REMOTE_RUNNER = r"""
import json
import os
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

argv = [
    payload["agent_bin"],
    "run",
    "--model",
    payload["model"],
    "--trust",
    "--never-ask",
    payload["prompt"],
]

def tail(value, limit=12000):
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", "replace")
    return str(value)[-limit:]

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
    lines = (proc.stdout or proc.stderr or "").strip().splitlines()
    summary = next((line.strip() for line in lines if line.strip()), "No output")[:500]
    result = {
        "task_id": payload["task_id"],
        "server": payload["server"],
        "status": status,
        "summary": summary,
        "returncode": proc.returncode,
        "stdout": tail(proc.stdout),
        "stderr": tail(proc.stderr),
        "changed_files": [],
        "checks": [],
        "risks": [] if proc.returncode == 0 else ["agent_returncode_nonzero"],
        "artifacts": [],
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
except subprocess.TimeoutExpired as exc:
    result = {
        "task_id": payload["task_id"],
        "server": payload["server"],
        "status": "timeout",
        "summary": "Agent task timed out",
        "stdout": tail(exc.stdout),
        "stderr": tail(exc.stderr),
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
        "summary": "Agent binary not found: " + payload["agent_bin"],
        "stdout": "",
        "stderr": "Agent binary not found: " + payload["agent_bin"],
        "changed_files": [],
        "checks": [],
        "risks": ["agent_binary_not_found"],
        "artifacts": [],
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }

result_path.write_text(json.dumps(result, ensure_ascii=True, indent=2), encoding="utf-8")
"""


ROLE_TASKS = {
    "home": "FormulaLM lead: inspect FormulaLM service contract, Proof v1 readiness, and missing logits dependencies. Do not train. Return exact next patch/task.",
    "main": "Release/backend lead: inspect main backend provider routing, FormulaLM cache/provider bug, nginx route state, and quality gates. Do not deploy. Return exact patch plan.",
    "uiap": "RAG lead: inspect RAG/knowledge API health, index state, and frontend/backend API contract gaps. Read-only.",
    "qjns": "Tools lead: inspect agent executor, worker completion contract, and safe tool-call boundaries. Read-only.",
    "9fts": "Inference lead: inspect inference node recovery, expected API target, and canary blockers. Read-only.",
    "kolibri": "Worker lead: inspect worker/backup readiness, queue execution gaps, and service health. Read-only.",
    "reserve242": "QA/security lead: inspect shell injection tests, no-secrets checks, and permission-boundary gaps. Read-only.",
    "hostvds-highload": "Build/release lead: inspect CI/build gate readiness, Rust/frontend/backend test gaps, and runner capacity. Read-only.",
    "hostvds-agent-01": "Backend lead: inspect FormulaLM provider contract, cache key provider isolation, RAG/API mismatch, and Intent.AUTO path. Read-only.",
    "hostvds-agent-02": "Frontend/design lead: inspect production chat UI, cluster status UX, provider selection, and browser QA baseline. Read-only.",
    "hostvds-agent-03": "Infra lead: inspect VPN/nginx/systemd/service routing, worker completion endpoint, and rollout blockers. Read-only.",
    "hostvds-agent-04": "Browser QA lead: define Playwright desktop/mobile smoke suite for chat, cluster, providers, and websocket. Read-only.",
    "hostvds-agent-05": "Security lead: audit orchestrator secrets handling, logs, prompts, and forbidden paths. Read-only.",
    "hostvds-agent-06": "Docs lead: inspect docs/orchestration/deployment drift and produce runbook update plan. Read-only.",
    "hostvds-agent-07": "FormulaLM evaluator: inspect Proof v1 metric contract, dataset split risks, and independent evaluator tasks. Read-only.",
    "hostvds-agent-08": "RAG evaluator: inspect retrieval baseline/eval fixtures and leakage risks. Read-only.",
    "hostvds-agent-09": "Canary/release lead: inspect smoke/rollback checklist and deployment safety gates. Read-only.",
    "hostvds-agent-10": "Edge/performance lead: inspect latency/load benchmark plan and Asia/HK edge readiness. Read-only.",
    "hostvds-paris-highload": "Reserve CI lead: inspect build burst readiness and fallback CI capacity. Read-only.",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    tmp.replace(path)


def load_agents() -> dict[str, Any]:
    return json.loads(AGENTS_FILE.read_text(encoding="utf-8"))


def initial_state() -> dict[str, Any]:
    return {
        "version": 1,
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "tasks": {},
        "events": [],
        "runs": {},
    }


def load_state() -> dict[str, Any]:
    if STATE_FILE.exists():
        state = load_json(STATE_FILE, initial_state())
    else:
        state = load_json(LEGACY_STATE_FILE, initial_state())
    state.setdefault("tasks", {})
    state.setdefault("events", [])
    state.setdefault("runs", {})
    return state


def save_state(state: dict[str, Any]) -> None:
    state["updated_at"] = utc_now()
    write_json(STATE_FILE, state)


def event(state: dict[str, Any], kind: str, payload: dict[str, Any]) -> None:
    state.setdefault("events", []).append({"at": utc_now(), "kind": kind, **payload})
    state["events"] = state["events"][-500:]


def enabled_servers(agents: dict[str, Any]) -> list[str]:
    return [name for name, cfg in agents.get("servers", {}).items() if cfg.get("enabled", True)]


def server_cfg(agents: dict[str, Any], server: str) -> dict[str, Any]:
    cfg = agents.get("servers", {}).get(server)
    if not cfg:
        raise SystemExit(f"Unknown server: {server}")
    return cfg


def ssh_base(cfg: dict[str, Any]) -> list[str]:
    argv = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=12",
        "-o",
        "ConnectionAttempts=1",
        "-o",
        "ServerAliveInterval=5",
        "-o",
        "ServerAliveCountMax=1",
    ]
    if cfg.get("ssh_port"):
        argv.extend(["-p", str(cfg["ssh_port"])])
    argv.append(str(cfg["ssh_alias"]))
    return argv


def run_limited(argv: list[str], *, input_text: str | None = None, timeout: int = 45) -> subprocess.CompletedProcess[str]:
    proc = subprocess.Popen(
        argv,
        stdin=subprocess.PIPE if input_text is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(input=input_text, timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        stdout, stderr = proc.communicate()
        return subprocess.CompletedProcess(argv, 124, stdout, stderr + "\nprocess group timed out")
    return subprocess.CompletedProcess(argv, proc.returncode, stdout, stderr)


def remote_root(server: str) -> str:
    return HOME_REMOTE_ROOT if server == "home" else DEFAULT_REMOTE_ROOT


def worktree_for(server: str, cfg: dict[str, Any], task_id: str) -> str:
    if server == "home":
        return "/srv/kolibri/repo"
    root = str(cfg.get("remote_worktree_root") or "/opt/kolibri-ai/agent-worktrees").rstrip("/")
    return f"{root}/{task_id}"


def prompt_for_task(task: dict[str, Any], cfg: dict[str, Any]) -> str:
    allowed = "\n".join(f"- {path}" for path in cfg.get("allowed_paths", []))
    return (
        "You are a bounded Kolibri development worker. Codex is the reviewer and release manager.\n"
        "Return a single structured JSON object with: status, summary, changed_files, checks, risks, artifacts, next_actions.\n"
        "Do not read .env, auth files, private keys, .ssh, .mimocode, tokens, passwords, or browser profiles.\n"
        "Do not deploy, push, restart production services, or modify files unless task mode is controlled_mutation.\n"
        f"Task mode: {task['mode']}.\n"
        f"Server role: {cfg.get('role')} / {cfg.get('deputy')}.\n"
        f"Allowed paths:\n{allowed}\n\n"
        f"Task:\n{task['prompt']}\n"
    )


def cmd_init(_: argparse.Namespace) -> int:
    state = load_state()
    save_state(state)
    print(json.dumps({"state": str(STATE_FILE), "status": "ready"}, indent=2))
    return 0


def cmd_enqueue(args: argparse.Namespace) -> int:
    agents = load_agents()
    state = load_state()
    servers = args.server or enabled_servers(agents)
    created = []
    for server in servers:
        cfg = server_cfg(agents, server)
        if not cfg.get("ssh_alias"):
            continue
        task_id = f"{args.wave}-{server}-{int(time.time())}"
        prompt = args.prompt or ROLE_TASKS.get(server) or f"Inspect {cfg.get('role')} and return next bounded task."
        task = {
            "id": task_id,
            "wave": args.wave,
            "server": server,
            "mode": args.mode,
            "backend": "mimo",
            "prompt": prompt,
            "status": "queued",
            "priority": args.priority,
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "timeout_seconds": args.timeout,
            "remote": {},
            "result": None,
        }
        state["tasks"][task_id] = task
        created.append(task_id)
    event(state, "enqueue", {"count": len(created), "wave": args.wave})
    save_state(state)
    print(json.dumps({"queued": len(created), "tasks": created}, indent=2))
    return 0


def dispatch_one(task: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    server = task["server"]
    run_id = f"factory-{task['id']}"
    root = remote_root(server)
    remote_dir = f"{root.rstrip('/')}/{run_id}/{server}"
    result_path = f"{remote_dir}/result.json"
    payload_path = f"{remote_dir}/payload.json"
    runner_path = f"{remote_dir}/runner.py"
    stdout_path = f"{remote_dir}/stdout.log"
    stderr_path = f"{remote_dir}/stderr.log"
    worktree = worktree_for(server, cfg, task["id"])
    agent_bin = cfg.get("mimo_bin") or "mimo"
    help_cmd = f"{shlex.quote(agent_bin)} --help | grep -E 'mimo run|run mimocode|run \\[message' >/dev/null"
    proc = run_limited(ssh_base(cfg) + [help_cmd], timeout=30)
    if proc.returncode != 0:
        return {
            "status": "dispatch_failed",
            "summary": "agent binary is not compatible with Mimocode run CLI",
            "stderr": proc.stderr[-2000:],
        }
    payload = {
        "task_id": task["id"],
        "server": server,
        "agent_bin": agent_bin,
        "worktree": worktree,
        "model": cfg.get("model") or load_agents().get("defaults", {}).get("model", "mimo/mimo-auto"),
        "prompt": prompt_for_task(task, cfg),
        "timeout_seconds": task.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS),
    }

    mkdir = ssh_base(cfg) + [f"mkdir -p {shlex.quote(remote_dir)} && cat > {shlex.quote(payload_path)}"]
    proc = run_limited(mkdir, input_text=json.dumps(payload), timeout=45)
    if proc.returncode != 0:
        return {"status": "dispatch_failed", "summary": "payload upload failed", "stderr": proc.stderr[-2000:]}

    upload = ssh_base(cfg) + [f"cat > {shlex.quote(runner_path)}"]
    proc = run_limited(upload, input_text=REMOTE_RUNNER, timeout=45)
    if proc.returncode != 0:
        return {"status": "dispatch_failed", "summary": "runner upload failed", "stderr": proc.stderr[-2000:]}

    start_cmd = (
        f"cd {shlex.quote(remote_dir)} && "
        f"(setsid python3 {shlex.quote(runner_path)} {shlex.quote(payload_path)} {shlex.quote(result_path)} "
        f"> {shlex.quote(stdout_path)} 2> {shlex.quote(stderr_path)} < /dev/null & echo $!)"
    )
    proc = run_limited(ssh_base(cfg) + [start_cmd], timeout=45)
    if proc.returncode != 0:
        return {"status": "dispatch_failed", "summary": "remote start failed", "stderr": proc.stderr[-2000:]}
    return {
        "status": "running",
        "pid": proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else "",
        "remote_dir": remote_dir,
        "result_path": result_path,
        "stdout_path": stdout_path,
        "stderr_path": stderr_path,
        "worktree": worktree,
        "started_at": utc_now(),
    }


def cmd_dispatch(args: argparse.Namespace) -> int:
    agents = load_agents()
    state = load_state()
    queued = [
        task for task in state["tasks"].values()
        if task.get("status") == "queued" and (not args.server or task.get("server") in args.server)
    ]
    queued.sort(key=lambda item: (-int(item.get("priority", 50)), item.get("created_at", "")))
    queued = queued[: args.limit]
    if not queued:
        print(json.dumps({"dispatched": 0, "status": "no_queued_tasks"}, indent=2))
        return 0

    def submit(task: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        return task["id"], dispatch_one(task, server_cfg(agents, task["server"]))

    results = []
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=args.max_workers)
    futures = [executor.submit(submit, task) for task in queued]
    try:
        for future in concurrent.futures.as_completed(futures):
            task_id, remote = future.result()
            task = state["tasks"][task_id]
            task["status"] = remote["status"]
            task["updated_at"] = utc_now()
            task["remote"] = remote
            results.append({"task_id": task_id, "server": task["server"], "status": remote["status"]})
            event(state, "dispatch_one", results[-1])
            save_state(state)
            print(json.dumps(results[-1]), flush=True)
    except KeyboardInterrupt:
        for future in futures:
            future.cancel()
        event(state, "dispatch_interrupted", {"completed": len(results), "requested": len(queued)})
        save_state(state)
        executor.shutdown(wait=False, cancel_futures=True)
        raise
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    event(state, "dispatch", {"count": len(results)})
    save_state(state)
    return 0 if all(item["status"] == "running" for item in results) else 1


def collect_one(task: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    result_path = task.get("remote", {}).get("result_path")
    if not result_path:
        return {"status": "missing_remote_result_path"}
    cmd = (
        f"if [ -f {shlex.quote(result_path)} ]; then "
        f"cat {shlex.quote(result_path)}; "
        "else echo __NO_RESULT__; "
        f"ps -p {shlex.quote(str(task.get('remote', {}).get('pid', '')))} -o pid=,stat=,etime=,args= 2>/dev/null || true; "
        "fi"
    )
    proc = run_limited(ssh_base(cfg) + [cmd], timeout=35)
    if proc.returncode != 0:
        return {"status": "collect_failed", "stderr": proc.stderr[-2000:]}
    stdout = proc.stdout.strip()
    if stdout.startswith("__NO_RESULT__"):
        return {"status": "running", "tail": stdout[-2000:]}
    try:
        result = json.loads(stdout)
    except json.JSONDecodeError:
        return {"status": "collect_failed", "summary": "invalid result json", "stdout": stdout[-2000:]}
    return {"status": result.get("status", "completed"), "result": result}


def cmd_collect(args: argparse.Namespace) -> int:
    agents = load_agents()
    state = load_state()
    running = [
        task for task in state["tasks"].values()
        if task.get("status") in {"running", "dispatch_failed"} and (not args.server or task.get("server") in args.server)
    ]
    results = []
    for task in running:
        if task.get("status") == "dispatch_failed":
            continue
        collected = collect_one(task, server_cfg(agents, task["server"]))
        if collected["status"] in {"collect_failed", "missing_remote_result_path"}:
            task.setdefault("collect_errors", []).append({"at": utc_now(), **collected})
            task["collect_errors"] = task["collect_errors"][-5:]
            if task.get("status") == "collect_failed":
                task["status"] = "running"
            task["updated_at"] = utc_now()
        elif collected["status"] != "running":
            task["status"] = collected["status"]
            task["result"] = collected.get("result") or collected
            task["updated_at"] = utc_now()
        results.append({"task_id": task["id"], "server": task["server"], "status": collected["status"]})
    event(state, "collect", {"count": len(results)})
    save_state(state)
    print(json.dumps({"collected": results}, indent=2))
    return 0


def summarize(state: dict[str, Any]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    by_server: dict[str, dict[str, int]] = {}
    blockers = []
    for task in state["tasks"].values():
        status = task.get("status", "unknown")
        counts[status] = counts.get(status, 0) + 1
        server = task.get("server", "unknown")
        by_server.setdefault(server, {})
        by_server[server][status] = by_server[server].get(status, 0) + 1
        result = task.get("result") or {}
        summary = str(result.get("summary") or result.get("stderr") or "")
        if status in {"failed", "timeout", "dispatch_failed", "collect_failed"}:
            blockers.append({"task_id": task["id"], "server": server, "status": status, "summary": summary[:240]})
    return {"counts": counts, "by_server": by_server, "blockers": blockers[:50]}


def cmd_report(_: argparse.Namespace) -> int:
    state = load_state()
    report = {
        "state": str(STATE_FILE),
        "generated_at": utc_now(),
        **summarize(state),
        "next_actions": [
            "Fix Mimo auth/bootstrap on servers reporting 403 before assigning product mutations.",
            "Keep product tasks read-only until one server completes a controlled mutation with diff and tests.",
            "Use dispatch/collect/report loop under systemd or nohup for continuous operation.",
        ],
    }
    write_json(FACTORY_STATE_DIR / "last_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def cmd_loop(args: argparse.Namespace) -> int:
    FACTORY_STATE_DIR.mkdir(parents=True, exist_ok=True)
    print(json.dumps({"status": "factory_loop_started", "interval": args.interval, "state": str(STATE_FILE)}), flush=True)
    while True:
        try:
            print(json.dumps({"status": "cycle_start", "at": utc_now()}), flush=True)
            cmd_dispatch(argparse.Namespace(limit=args.limit, max_workers=args.max_workers, server=args.server))
            cmd_collect(argparse.Namespace(server=args.server))
            cmd_report(argparse.Namespace())
            print(json.dumps({"status": "cycle_complete", "at": utc_now()}), flush=True)
        except SystemExit as exc:
            state = load_state()
            event(state, "loop_system_exit", {"code": exc.code})
            save_state(state)
            print(json.dumps({"status": "loop_system_exit", "code": exc.code}), flush=True)
        except Exception as exc:
            state = load_state()
            event(state, "loop_error", {"summary": str(exc)})
            save_state(state)
            print(json.dumps({"status": "loop_error", "error": str(exc)}), flush=True)
        time.sleep(args.interval)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Kolibri agent factory")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init").set_defaults(func=cmd_init)

    enqueue = sub.add_parser("enqueue-wave")
    enqueue.add_argument("--wave", default="bootstrap")
    enqueue.add_argument("--mode", choices=["read_only", "controlled_mutation", "health", "report"], default="read_only")
    enqueue.add_argument("--server", action="append")
    enqueue.add_argument("--prompt")
    enqueue.add_argument("--priority", type=int, default=50)
    enqueue.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    enqueue.set_defaults(func=cmd_enqueue)

    dispatch = sub.add_parser("dispatch")
    dispatch.add_argument("--limit", type=int, default=8)
    dispatch.add_argument("--max-workers", type=int, default=6)
    dispatch.add_argument("--server", action="append")
    dispatch.set_defaults(func=cmd_dispatch)

    collect = sub.add_parser("collect")
    collect.add_argument("--server", action="append")
    collect.set_defaults(func=cmd_collect)

    sub.add_parser("report").set_defaults(func=cmd_report)

    loop = sub.add_parser("loop")
    loop.add_argument("--interval", type=int, default=300)
    loop.add_argument("--limit", type=int, default=8)
    loop.add_argument("--max-workers", type=int, default=6)
    loop.add_argument("--server", action="append")
    loop.set_defaults(func=cmd_loop)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
