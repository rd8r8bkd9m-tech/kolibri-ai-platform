#!/usr/bin/env python3
"""Persistent Kolibri remote agent host."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STOP = False


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def request(method: str, url: str, body: dict[str, Any] | None = None, timeout: int = 20) -> Any:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 204:
                return None
            payload = resp.read().decode("utf-8")
            return json.loads(payload) if payload else None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"{method} {url} failed: HTTP {exc.code}: {detail}") from exc


def machine_stats() -> dict[str, Any]:
    disk = shutil.disk_usage("/")
    ram = {}
    try:
        meminfo = Path("/proc/meminfo").read_text(encoding="utf-8")
        for line in meminfo.splitlines():
            name, value = line.split(":", 1)
            if name in {"MemTotal", "MemAvailable"}:
                ram[name] = value.strip()
    except OSError:
        pass
    return {
        "cpu": os.cpu_count(),
        "ram": ram,
        "disk": {"total": disk.total, "used": disk.used, "free": disk.free},
    }


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


class AgentHost:
    def __init__(self, args: argparse.Namespace):
        self.control_url = args.control_url.rstrip("/")
        self.node_id = args.node_id
        self.agent_id = args.agent_id or f"{args.node_id}-agent-host"
        self.capabilities = [item for item in args.capabilities.split(",") if item]
        self.repo_url = args.repo_url
        self.work_root = Path(args.work_root)
        self.artifact_root = Path(args.artifact_root)
        self.heartbeat_interval = args.heartbeat_interval
        self.lease_refresh = args.lease_refresh
        self.max_inflight = args.max_inflight
        self.hostname = platform.node()
        self.pid = os.getpid()
        self.work_root.mkdir(parents=True, exist_ok=True)
        self.artifact_root.mkdir(parents=True, exist_ok=True)

    def post(self, path: str, body: dict[str, Any]) -> Any:
        return request("POST", f"{self.control_url}{path}", body)

    def get(self, path: str) -> Any:
        return request("GET", f"{self.control_url}{path}")

    def register(self) -> None:
        body = {
            "node_id": self.node_id,
            "hostname": self.hostname,
            "agent_id": self.agent_id,
            "pid": self.pid,
            "capabilities": self.capabilities,
            **machine_stats(),
        }
        self.post("/v1/nodes/register", body)

    def node_heartbeat(self, active_task: str | None = None) -> None:
        body = {
            "node_id": self.node_id,
            "hostname": self.hostname,
            "agent_id": self.agent_id,
            "pid": self.pid,
            "capabilities": self.capabilities,
            "active_task": active_task,
            **machine_stats(),
        }
        self.post(f"/v1/nodes/{self.node_id}/heartbeat", body)

    def task_heartbeat(self, task: dict[str, Any], worktree: Path, branch: str | None, logs: dict[str, str], pid: int | None = None) -> dict[str, Any]:
        body = {
            "state": "running",
            "pid": pid or self.pid,
            "worktree": str(worktree),
            "branch": branch,
            "log_paths": logs,
        }
        return self.post(f"/v1/tasks/{task['task_id']}/heartbeat", body)

    def lease(self) -> dict[str, Any] | None:
        return self.post("/v1/tasks/lease", {
            "node_id": self.node_id,
            "agent_id": self.agent_id,
            "capabilities": self.capabilities,
        })

    def run_command(
        self,
        command: list[str],
        cwd: Path,
        stdout_path: Path,
        stderr_path: Path,
        task: dict[str, Any],
        branch: str | None,
        logs: dict[str, str],
        env: dict[str, str] | None = None,
    ) -> None:
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)
        with stdout_path.open("ab") as stdout, stderr_path.open("ab") as stderr:
            stdout.write(f"\n$ {' '.join(command)}\n".encode("utf-8"))
            stdout.flush()
            proc = subprocess.Popen(command, cwd=str(cwd), stdout=stdout, stderr=stderr, env=merged_env)
            last_refresh = 0.0
            while proc.poll() is None:
                if STOP:
                    proc.terminate()
                    raise RuntimeError("agent host received SIGTERM")
                if time.time() - last_refresh >= self.lease_refresh:
                    self.task_heartbeat(task, cwd, branch, logs, proc.pid)
                    last_refresh = time.time()
                time.sleep(2)
            if proc.returncode != 0:
                raise RuntimeError(f"command failed with rc={proc.returncode}: {' '.join(command)}")

    def write_result(self, artifact_dir: Path, result: dict[str, Any]) -> Path:
        result_path = artifact_dir / "result.json"
        result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest = []
        for path in sorted(artifact_dir.rglob("*")):
            if path.is_file():
                manifest.append({"path": str(path), "sha256": sha256_file(path), "bytes": path.stat().st_size})
        (artifact_dir / "artifact-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return result_path

    def complete(self, task: dict[str, Any], result: dict[str, Any], result_path: Path) -> None:
        self.post(f"/v1/tasks/{task['task_id']}/complete", {
            "result_reference": str(result_path),
            "result": result,
        })

    def fail(self, task: dict[str, Any], error_type: str, error: str, result: dict[str, Any] | None, result_path: Path | None, retry: bool = True) -> None:
        self.post(f"/v1/tasks/{task['task_id']}/fail", {
            "error_type": error_type,
            "error": error,
            "result": result,
            "result_reference": str(result_path) if result_path else None,
            "retry": retry,
        })

    def prepare_dirs(self, task: dict[str, Any]) -> tuple[Path, Path, dict[str, str]]:
        task_id = task["task_id"]
        attempt_id = task.get("attempt_id") or f"{task_id}-attempt-{task.get('attempt', 1)}"
        worktree = self.work_root / task_id / attempt_id / "repo"
        artifact_dir = self.artifact_root / task_id / attempt_id
        if worktree.exists():
            shutil.rmtree(worktree)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        logs = {
            "stdout": str(artifact_dir / "stdout.log"),
            "stderr": str(artifact_dir / "stderr.log"),
        }
        return worktree, artifact_dir, logs

    def run_read_only_probe(self, task: dict[str, Any]) -> dict[str, Any]:
        worktree, artifact_dir, logs = self.prepare_dirs(task)
        worktree.mkdir(parents=True, exist_ok=True)
        self.task_heartbeat(task, worktree, None, logs)
        result = {
            "node_id": self.node_id,
            "hostname": self.hostname,
            "task_id": task["task_id"],
            "agent_id": self.agent_id,
            "attempt_id": task.get("attempt_id"),
            "pid": self.pid,
            "heartbeat_at": utc_now(),
            "worktree": str(worktree),
            "branch": None,
            "log_paths": logs,
            "result_path": str(artifact_dir / "result.json"),
            "status": "completed",
            "kind": "read_only_probe",
            "message": "read-only probe completed",
        }
        result_path = self.write_result(artifact_dir, result)
        result["result_path"] = str(result_path)
        return result

    def run_impl_factory_smoke(self, task: dict[str, Any]) -> dict[str, Any]:
        envelope = task.get("envelope", {})
        branch = envelope.get("branch", f"agent/{task['task_id']}/impl/factory-smoke")
        base_ref = envelope.get("base_ref", "origin/main")
        smoke_path = envelope.get("smoke_path", "tests/test_factory_smoke.py")
        worktree, artifact_dir, logs = self.prepare_dirs(task)
        worktree.parent.mkdir(parents=True, exist_ok=True)
        stdout_path = Path(logs["stdout"])
        stderr_path = Path(logs["stderr"])
        self.task_heartbeat(task, worktree, branch, logs)

        git_env = {"GIT_TERMINAL_PROMPT": "0"}
        self.run_command(["git", "clone", self.repo_url, str(worktree)], worktree.parent, stdout_path, stderr_path, task, branch, logs, git_env)
        self.run_command(["git", "fetch", "origin"], worktree, stdout_path, stderr_path, task, branch, logs, git_env)
        self.run_command(["git", "checkout", "-B", branch, base_ref], worktree, stdout_path, stderr_path, task, branch, logs, git_env)

        test_file = worktree / smoke_path
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text(
            "def test_factory_smoke_marker():\n"
            "    assert 'kolibri-factory-mvp' == 'kolibri-factory-mvp'\n",
            encoding="utf-8",
        )
        self.run_command([
            "python3", "-c",
            "import compileall,pathlib,sys; paths=[p for p in ('backend','infra','scripts','ops') if pathlib.Path(p).exists()]; sys.exit(0 if compileall.compile_dir('.', quiet=1, maxlevels=0) and all(compileall.compile_dir(p, quiet=1) for p in paths) else 1)",
        ], worktree, stdout_path, stderr_path, task, branch, logs)
        venv_dir = artifact_dir / "venv"
        self.run_command(["python3", "-m", "venv", str(venv_dir)], worktree, stdout_path, stderr_path, task, branch, logs)
        self.run_command([str(venv_dir / "bin" / "python"), "-m", "pip", "install", "--upgrade", "pip", "pytest"], worktree, stdout_path, stderr_path, task, branch, logs)
        self.run_command([str(venv_dir / "bin" / "python"), "-m", "pytest", "-q", "tests/test_factory_smoke.py"], worktree, stdout_path, stderr_path, task, branch, logs)
        self.run_command(["git", "add", smoke_path], worktree, stdout_path, stderr_path, task, branch, logs)
        self.run_command(["git", "commit", "-m", "test: add factory smoke"], worktree, stdout_path, stderr_path, task, branch, logs)
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(worktree), text=True).strip()
        self.run_command(["git", "push", "-u", "origin", branch], worktree, stdout_path, stderr_path, task, branch, logs, git_env)

        pr_url = None
        if shutil.which("gh"):
            self.run_command([
                "gh", "pr", "create",
                "--base", envelope.get("base_branch", "main"),
                "--head", branch,
                "--title", envelope.get("pr_title", "Factory MVP smoke test"),
                "--body", envelope.get("pr_body", "Adds the Factory MVP smoke test from a persistent remote agent."),
            ], worktree, stdout_path, stderr_path, task, branch, logs, git_env)
            pr_url = subprocess.check_output(["gh", "pr", "view", "--json", "url", "-q", ".url"], cwd=str(worktree), text=True).strip()
        else:
            raise RuntimeError("github_cli_missing: gh is required on remote node to create the PR without exposing local credentials")

        result = {
            "node_id": self.node_id,
            "hostname": self.hostname,
            "task_id": task["task_id"],
            "agent_id": self.agent_id,
            "attempt_id": task.get("attempt_id"),
            "pid": self.pid,
            "heartbeat_at": utc_now(),
            "worktree": str(worktree),
            "branch": branch,
            "commit": commit,
            "pull_request_url": pr_url,
            "log_paths": logs,
            "result_path": str(artifact_dir / "result.json"),
            "status": "completed",
            "changed_files": [smoke_path],
            "checks": ["python3 -m compileall -q backend infra scripts ops", "python3 -m pytest -q tests/test_factory_smoke.py"],
        }
        result_path = self.write_result(artifact_dir, result)
        result["result_path"] = str(result_path)
        return result

    def run_review_pr(self, task: dict[str, Any]) -> dict[str, Any]:
        envelope = task.get("envelope", {})
        branch = envelope.get("branch")
        pr_url = envelope.get("pull_request_url")
        if not branch:
            raise RuntimeError("review task missing branch")
        worktree, artifact_dir, logs = self.prepare_dirs(task)
        worktree.parent.mkdir(parents=True, exist_ok=True)
        stdout_path = Path(logs["stdout"])
        stderr_path = Path(logs["stderr"])
        self.task_heartbeat(task, worktree, branch, logs)
        git_env = {"GIT_TERMINAL_PROMPT": "0"}
        self.run_command(["git", "clone", self.repo_url, str(worktree)], worktree.parent, stdout_path, stderr_path, task, branch, logs, git_env)
        self.run_command(["git", "fetch", "origin", branch], worktree, stdout_path, stderr_path, task, branch, logs, git_env)
        self.run_command(["git", "checkout", "-B", f"review/{task['task_id']}", "FETCH_HEAD"], worktree, stdout_path, stderr_path, task, branch, logs, git_env)
        diff_files = subprocess.check_output(["git", "diff", "--name-only", "origin/main...HEAD"], cwd=str(worktree), text=True).splitlines()
        blocked = [path for path in diff_files if path.startswith(".env") or path.endswith(".key") or path.endswith(".pem")]
        status = "CHANGES_REQUESTED" if blocked else "APPROVED"
        self.run_command([
            "python3", "-c",
            "import compileall,pathlib,sys; paths=[p for p in ('backend','infra','scripts','ops') if pathlib.Path(p).exists()]; sys.exit(0 if compileall.compile_dir('.', quiet=1, maxlevels=0) and all(compileall.compile_dir(p, quiet=1) for p in paths) else 1)",
        ], worktree, stdout_path, stderr_path, task, branch, logs)
        if (worktree / "tests").exists():
            venv_dir = artifact_dir / "venv"
            self.run_command(["python3", "-m", "venv", str(venv_dir)], worktree, stdout_path, stderr_path, task, branch, logs)
            self.run_command([str(venv_dir / "bin" / "python"), "-m", "pip", "install", "--upgrade", "pip", "pytest"], worktree, stdout_path, stderr_path, task, branch, logs)
            self.run_command([str(venv_dir / "bin" / "python"), "-m", "pytest", "-q"], worktree, stdout_path, stderr_path, task, branch, logs)
        github_review = "skipped: gh unavailable"
        if shutil.which("gh"):
            event = "APPROVE" if status == "APPROVED" else "REQUEST_CHANGES"
            self.run_command(["gh", "pr", "review", pr_url or branch, f"--{event.lower().replace('_', '-')}", "--body", status], worktree, stdout_path, stderr_path, task, branch, logs, git_env)
            github_review = "submitted"
        result = {
            "node_id": self.node_id,
            "hostname": self.hostname,
            "task_id": task["task_id"],
            "agent_id": self.agent_id,
            "attempt_id": task.get("attempt_id"),
            "pid": self.pid,
            "heartbeat_at": utc_now(),
            "worktree": str(worktree),
            "branch": branch,
            "pull_request_url": pr_url,
            "status": status,
            "github_review": github_review,
            "changed_files": diff_files,
            "findings": blocked,
            "log_paths": logs,
            "result_path": str(artifact_dir / "result.json"),
        }
        result_path = self.write_result(artifact_dir, result)
        result["result_path"] = str(result_path)
        return result

    def run_task(self, task: dict[str, Any]) -> None:
        result_path = None
        result = None
        try:
            kind = task.get("kind")
            if kind == "impl_factory_smoke":
                result = self.run_impl_factory_smoke(task)
            elif kind == "review_pr":
                result = self.run_review_pr(task)
            elif kind == "read_only_probe":
                result = self.run_read_only_probe(task)
            else:
                raise RuntimeError(f"unsupported task kind: {kind}")
            result_path = Path(result["result_path"])
            self.complete(task, result, result_path)
        except Exception as exc:
            task_id = task["task_id"]
            attempt_id = task.get("attempt_id") or f"{task_id}-attempt-{task.get('attempt', 1)}"
            artifact_dir = self.artifact_root / task_id / attempt_id
            artifact_dir.mkdir(parents=True, exist_ok=True)
            result = {
                "node_id": self.node_id,
                "hostname": self.hostname,
                "task_id": task_id,
                "agent_id": self.agent_id,
                "attempt_id": attempt_id,
                "pid": self.pid,
                "status": "failed",
                "error": str(exc),
                "completed_at": utc_now(),
            }
            result_path = self.write_result(artifact_dir, result)
            retry = int(task.get("attempt", 0)) < int(task.get("max_retries", 3))
            self.fail(task, "runtime_error", str(exc), result, result_path, retry=retry)

    def loop(self) -> None:
        self.register()
        last_node_heartbeat = 0.0
        while not STOP:
            if time.time() - last_node_heartbeat >= self.heartbeat_interval:
                self.node_heartbeat()
                last_node_heartbeat = time.time()
            task = self.lease()
            if task:
                self.node_heartbeat(active_task=task["task_id"])
                self.run_task(task)
                self.node_heartbeat()
            time.sleep(2)


def handle_stop(signum: int, frame: Any) -> None:
    del signum, frame
    global STOP
    STOP = True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--control-url", default=os.environ.get("KOLIBRI_FACTORY_CONTROL_URL", "http://10.99.0.2:9101"))
    parser.add_argument("--node-id", default=os.environ.get("KOLIBRI_NODE_ID", platform.node()))
    parser.add_argument("--agent-id", default=os.environ.get("KOLIBRI_AGENT_ID"))
    parser.add_argument("--capabilities", default=os.environ.get("KOLIBRI_AGENT_CAPABILITIES", "read_only_probe"))
    parser.add_argument("--repo-url", default=os.environ.get("KOLIBRI_REPO_URL", "https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform.git"))
    parser.add_argument("--work-root", default=os.environ.get("KOLIBRI_AGENT_WORK_ROOT", "/var/lib/kolibri-agent/worktrees"))
    parser.add_argument("--artifact-root", default=os.environ.get("KOLIBRI_AGENT_ARTIFACT_ROOT", "/var/lib/kolibri-agent/artifacts"))
    parser.add_argument("--heartbeat-interval", type=int, default=int(os.environ.get("KOLIBRI_HEARTBEAT_INTERVAL", "10")))
    parser.add_argument("--lease-refresh", type=int, default=int(os.environ.get("KOLIBRI_LEASE_REFRESH", "20")))
    parser.add_argument("--max-inflight", type=int, default=int(os.environ.get("KOLIBRI_MAX_INFLIGHT", "1")))
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, handle_stop)
    signal.signal(signal.SIGINT, handle_stop)
    AgentHost(args).loop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
