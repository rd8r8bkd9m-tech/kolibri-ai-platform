#!/usr/bin/env python3
"""Patch deployed kolibri-agent-host to support admin task kinds.

Run on each server:
    python3 /tmp/patch_agent_host_admin.py /usr/local/bin/kolibri-agent-host

Adds: admin_exec, admin_service, admin_git, admin_rotate_keys
"""
import sys
import re
from pathlib import Path

ADMIN_TASK_KINDS = {"admin_exec", "admin_service", "admin_git", "admin_rotate_keys"}

ADMIN_HANDLER_METHODS = '''
    # ── Admin task handlers ─────────────────────────────────────────

    def run_admin_exec(self, task: dict[str, Any]) -> dict[str, Any]:
        envelope = task.get("envelope", {})
        objective = json.loads(envelope.get("objective") or "{}")
        command = objective.get("command", [])
        cwd = Path(objective.get("cwd", "/"))
        timeout = int(objective.get("timeout", 30))
        extra_env = objective.get("env", {})
        worktree, artifact_dir, logs = self.prepare_dirs(task)
        worktree.mkdir(parents=True, exist_ok=True)
        stdout_path = Path(logs["stdout"])
        stderr_path = Path(logs["stderr"])
        self.task_heartbeat(task, worktree, None, logs)
        merged_env = agent_child_environment(extra_env)
        display_command = " ".join(command) if isinstance(command, list) else str(command)
        try:
            with stdout_path.open("ab") as stdout_f, stderr_path.open("ab") as stderr_f:
                stdout_f.write(("$ " + display_command + "\\\\n").encode())
                stdout_f.flush()
                if isinstance(command, str):
                    import shlex
                    command = shlex.split(command)
                proc = subprocess.run(
                    command, cwd=str(cwd), capture_output=True, text=True,
                    timeout=timeout, env=merged_env,
                )
                stdout_f.write(proc.stdout.encode())
                stderr_f.write(proc.stderr.encode())
            result = {
                "node_id": self.node_id, "hostname": self.hostname,
                "task_id": task["task_id"], "agent_id": self.agent_id,
                "attempt_id": task.get("attempt_id"), "pid": self.pid,
                "heartbeat_at": utc_now(), "worktree": str(worktree),
                "branch": None, "log_paths": logs,
                "result_path": str(artifact_dir / "result.json"),
                "status": "completed" if proc.returncode == 0 else "failed",
                "kind": "admin_exec",
                "returncode": proc.returncode,
                "stdout": proc.stdout[-4096:],
                "stderr": proc.stderr[-4096:],
            }
        except subprocess.TimeoutExpired:
            result = {
                "node_id": self.node_id, "hostname": self.hostname,
                "task_id": task["task_id"], "agent_id": self.agent_id,
                "attempt_id": task.get("attempt_id"), "pid": self.pid,
                "heartbeat_at": utc_now(), "worktree": str(worktree),
                "branch": None, "log_paths": logs,
                "result_path": str(artifact_dir / "result.json"),
                "status": "failed", "kind": "admin_exec",
                "error_type": "timeout",
                "error": f"command timed out after {timeout}s",
            }
        except Exception as exc:
            result = {
                "node_id": self.node_id, "hostname": self.hostname,
                "task_id": task["task_id"], "agent_id": self.agent_id,
                "attempt_id": task.get("attempt_id"), "pid": self.pid,
                "heartbeat_at": utc_now(), "worktree": str(worktree),
                "branch": None, "log_paths": logs,
                "result_path": str(artifact_dir / "result.json"),
                "status": "failed", "kind": "admin_exec",
                "error_type": "runtime_error", "error": str(exc),
            }
        result_path = self.write_result(artifact_dir, result)
        result["result_path"] = str(result_path)
        return result

    def run_admin_service(self, task: dict[str, Any]) -> dict[str, Any]:
        envelope = task.get("envelope", {})
        objective = json.loads(envelope.get("objective") or "{}")
        action = objective.get("action", "status")
        service = objective.get("service", "")
        worktree, artifact_dir, logs = self.prepare_dirs(task)
        worktree.mkdir(parents=True, exist_ok=True)
        self.task_heartbeat(task, worktree, None, logs)
        cmd_map = {
            "start": ["systemctl", "start", service],
            "stop": ["systemctl", "stop", service],
            "restart": ["systemctl", "restart", service],
            "status": ["systemctl", "status", service],
            "enable": ["systemctl", "enable", service],
            "disable": ["systemctl", "disable", service],
        }
        command = cmd_map.get(action)
        if not command:
            result = {
                "node_id": self.node_id, "hostname": self.hostname,
                "task_id": task["task_id"], "agent_id": self.agent_id,
                "attempt_id": task.get("attempt_id"), "pid": self.pid,
                "heartbeat_at": utc_now(), "worktree": str(worktree),
                "branch": None, "log_paths": logs,
                "result_path": str(artifact_dir / "result.json"),
                "status": "failed", "kind": "admin_service",
                "error_type": "invalid_action", "error": f"unknown action: {action}",
            }
            result_path = self.write_result(artifact_dir, result)
            result["result_path"] = str(result_path)
            return result
        stdout_path = Path(logs["stdout"])
        stderr_path = Path(logs["stderr"])
        try:
            with stdout_path.open("ab") as stdout_f, stderr_path.open("ab") as stderr_f:
                proc = subprocess.run(command, capture_output=True, text=True, timeout=30)
                stdout_f.write(proc.stdout.encode())
                stderr_f.write(proc.stderr.encode())
            result = {
                "node_id": self.node_id, "hostname": self.hostname,
                "task_id": task["task_id"], "agent_id": self.agent_id,
                "attempt_id": task.get("attempt_id"), "pid": self.pid,
                "heartbeat_at": utc_now(), "worktree": str(worktree),
                "branch": None, "log_paths": logs,
                "result_path": str(artifact_dir / "result.json"),
                "status": "completed" if proc.returncode == 0 else "failed",
                "kind": "admin_service", "action": action, "service": service,
                "returncode": proc.returncode,
                "stdout": proc.stdout[-4096:],
                "stderr": proc.stderr[-4096:],
            }
        except Exception as exc:
            result = {
                "node_id": self.node_id, "hostname": self.hostname,
                "task_id": task["task_id"], "agent_id": self.agent_id,
                "attempt_id": task.get("attempt_id"), "pid": self.pid,
                "heartbeat_at": utc_now(), "worktree": str(worktree),
                "branch": None, "log_paths": logs,
                "result_path": str(artifact_dir / "result.json"),
                "status": "failed", "kind": "admin_service",
                "error_type": "runtime_error", "error": str(exc),
            }
        result_path = self.write_result(artifact_dir, result)
        result["result_path"] = str(result_path)
        return result

    def run_admin_git(self, task: dict[str, Any]) -> dict[str, Any]:
        envelope = task.get("envelope", {})
        objective = json.loads(envelope.get("objective") or "{}")
        action = objective.get("action", "status")
        repo_path = Path(objective.get("path", "/opt/kolibri-ai-platform"))
        branch = objective.get("branch")
        remote = objective.get("remote", "origin")
        worktree_dir, artifact_dir, logs = self.prepare_dirs(task)
        worktree_dir.mkdir(parents=True, exist_ok=True)
        self.task_heartbeat(task, worktree_dir, None, logs)
        cmd_map = {
            "status": ["git", "-C", str(repo_path), "status", "--short"],
            "pull": ["git", "-C", str(repo_path), "pull", remote, branch or "main"],
            "diff": ["git", "-C", str(repo_path), "diff", "HEAD~5"],
            "log": ["git", "-C", str(repo_path), "log", "--oneline", "-20"],
            "stash": ["git", "-C", str(repo_path), "stash", "list"],
        }
        command = cmd_map.get(action)
        if not command:
            command = ["git", "-C", str(repo_path), action]
        stdout_path = Path(logs["stdout"])
        stderr_path = Path(logs["stderr"])
        try:
            with stdout_path.open("ab") as stdout_f, stderr_path.open("ab") as stderr_f:
                proc = subprocess.run(command, capture_output=True, text=True, timeout=60)
                stdout_f.write(proc.stdout.encode())
                stderr_f.write(proc.stderr.encode())
            result = {
                "node_id": self.node_id, "hostname": self.hostname,
                "task_id": task["task_id"], "agent_id": self.agent_id,
                "attempt_id": task.get("attempt_id"), "pid": self.pid,
                "heartbeat_at": utc_now(), "worktree": str(worktree_dir),
                "branch": None, "log_paths": logs,
                "result_path": str(artifact_dir / "result.json"),
                "status": "completed" if proc.returncode == 0 else "failed",
                "kind": "admin_git", "action": action,
                "returncode": proc.returncode,
                "stdout": proc.stdout[-8192:],
                "stderr": proc.stderr[-4096:],
            }
        except Exception as exc:
            result = {
                "node_id": self.node_id, "hostname": self.hostname,
                "task_id": task["task_id"], "agent_id": self.agent_id,
                "attempt_id": task.get("attempt_id"), "pid": self.pid,
                "heartbeat_at": utc_now(), "worktree": str(worktree_dir),
                "branch": None, "log_paths": logs,
                "result_path": str(artifact_dir / "result.json"),
                "status": "failed", "kind": "admin_git",
                "error_type": "runtime_error", "error": str(exc),
            }
        result_path = self.write_result(artifact_dir, result)
        result["result_path"] = str(result_path)
        return result

    def run_admin_rotate_keys(self, task: dict[str, Any]) -> dict[str, Any]:
        envelope = task.get("envelope", {})
        objective = json.loads(envelope.get("objective") or "{}")
        reason = objective.get("reason", "operator_rotation")
        worktree, artifact_dir, logs = self.prepare_dirs(task)
        worktree.mkdir(parents=True, exist_ok=True)
        self.task_heartbeat(task, worktree, None, logs)
        try:
            import secrets as _secrets
            new_token = _secrets.token_hex(32)
            token_path = Path("/etc/kolibri/runner-access.json")
            if token_path.exists():
                import shutil as _shutil
                backup = token_path.with_suffix(".json.bak")
                _shutil.copy2(token_path, backup)
            result = {
                "node_id": self.node_id, "hostname": self.hostname,
                "task_id": task["task_id"], "agent_id": self.agent_id,
                "attempt_id": task.get("attempt_id"), "pid": self.pid,
                "heartbeat_at": utc_now(), "worktree": str(worktree),
                "branch": None, "log_paths": logs,
                "result_path": str(artifact_dir / "result.json"),
                "status": "completed", "kind": "admin_rotate_keys",
                "reason": reason,
                "message": f"Key rotation prepared. Backup created. New token generated.",
                "requires_restart": True,
            }
        except Exception as exc:
            result = {
                "node_id": self.node_id, "hostname": self.hostname,
                "task_id": task["task_id"], "agent_id": self.agent_id,
                "attempt_id": task.get("attempt_id"), "pid": self.pid,
                "heartbeat_at": utc_now(), "worktree": str(worktree),
                "branch": None, "log_paths": logs,
                "result_path": str(artifact_dir / "result.json"),
                "status": "failed", "kind": "admin_rotate_keys",
                "error_type": "runtime_error", "error": str(exc),
            }
        result_path = self.write_result(artifact_dir, result)
        result["result_path"] = str(result_path)
        return result
'''

ADMIN_DISPATCH_CASES = '''
            elif kind == "admin_exec":
                result = self.run_admin_exec(task)
            elif kind == "admin_service":
                result = self.run_admin_service(task)
            elif kind == "admin_git":
                result = self.run_admin_git(task)
            elif kind == "admin_rotate_keys":
                result = self.run_admin_rotate_keys(task)
'''


def patch_agent_host(path: Path) -> bool:
    content = path.read_text(encoding="utf-8")

    # 1. Add admin kinds to SUPPORTED_TASK_KINDS
    admin_kinds_str = ", ".join(f'"{k}"' for k in sorted(ADMIN_TASK_KINDS))
    if "admin_exec" in content:
        print(f"  SKIP: {path} already patched (admin_exec found)")
        return False

    # Insert after LEASE_HEARTBEAT_PROBE_KIND line in SUPPORTED_TASK_KINDS
    pattern = r'(LEASE_HEARTBEAT_PROBE_KIND,\n\} \| set\(RELEASE_TASK_KINDS\))'
    replacement = f'LEASE_HEARTBEAT_PROBE_KIND,\n    {admin_kinds_str},\n}} | set(RELEASE_TASK_KINDS)'
    new_content, count = re.subn(pattern, replacement, content, count=1)
    if count == 0:
        print(f"  WARN: Could not find SUPPORTED_TASK_KINDS pattern, trying alt...")
        # Try alternate pattern
        pattern2 = r'(\} \| set\(RELEASE_TASK_KINDS\)\nNO_PUSH_FLAGS)'
        replacement2 = f'{admin_kinds_str},\n}} | set(RELEASE_TASK_KINDS)\nNO_PUSH_FLAGS'
        new_content, count = re.subn(pattern2, replacement2, content, count=1)

    if count == 0:
        print(f"  ERROR: Could not patch SUPPORTED_TASK_KINDS in {path}")
        return False

    # 2. Add handler methods before run_task method
    run_task_pattern = r'(\n    def run_task\(self, task: dict\[str, Any\]\) -> None:)'
    new_content, count2 = re.subn(run_task_pattern, f'\n{ADMIN_HANDLER_METHODS}\n\\1', new_content, count=1)
    if count2 == 0:
        print(f"  ERROR: Could not find run_task method in {path}")
        return False

    # 3. Add dispatch cases in run_task before the else clause
    else_pattern = r'(            else:\n                raise RuntimeError\(f"unsupported task kind reached dispatch: \{kind\}"\))'
    new_content, count3 = re.subn(else_pattern, f'{ADMIN_DISPATCH_CASES}\n\\1', new_content, count=1)
    if count3 == 0:
        print(f"  ERROR: Could not find dispatch else clause in {path}")
        return False

    # Backup and write
    backup = path.with_suffix(".py.bak")
    backup.write_bytes(path.read_bytes())
    path.write_text(new_content, encoding="utf-8")
    print(f"  OK: Patched {path} ({len(new_content)} bytes, backup at {backup})")
    return True


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/usr/local/bin/kolibri-agent-host")
    if not target.exists():
        print(f"ERROR: {target} not found")
        sys.exit(1)
    print(f"Patching {target}...")
    ok = patch_agent_host(target)
    sys.exit(0 if ok else 1)
