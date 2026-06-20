#!/usr/bin/env python3
"""Safe task runner for Kolibri Mimo/OpenClaw agents.

The runner is intentionally conservative:
- Agent CLIs are always invoked through argv, never through shell interpolation.
- Prompts are redacted before they are written to logs.
- Remote prompts are sent over SSH stdin to a small Python launcher, not placed
  in the remote shell command.
- The unsafe Mimo permission bypass is disabled unless the caller explicitly
  opts in with --allow-unsafe and the task manifest allows it.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_AGENTS_FILE = PROJECT_DIR / "ops" / "agents.yml"
DEFAULT_LOG_DIR = PROJECT_DIR / "logs" / "agent-runs"
DEFAULT_AGENT_BACKEND = "mimo"
DEFAULT_MODEL = "mimo/mimo-auto"
DEFAULT_TIMEOUT = 300
QUALITY_LIST_FIELDS = {
    "scope",
    "out_of_scope",
    "acceptance_criteria",
    "verification_steps",
    "deliverables",
    "stop_conditions",
}

SECRET_KEY_RE = re.compile(r"(api[_-]?key|token|secret|password|passwd|private[_-]?key)", re.I)
SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b([A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|PASSWD|API_KEY|PRIVATE_KEY)[A-Z0-9_]*)\s*=\s*([^\s]+)"
)


class RunnerError(RuntimeError):
    """User-facing runner failure."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RunnerError(f"File not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RunnerError(f"Invalid JSON in {path}: {exc}") from exc


def load_agents(path: Path) -> dict[str, Any]:
    """Load ops/agents.yml.

    The repository stores this file as YAML-compatible JSON so the runner does
    not need a PyYAML dependency on production servers. If PyYAML is available,
    plain YAML remains supported.
    """

    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        try:
            import yaml  # type: ignore
        except Exception as exc:
            raise RunnerError(
                f"{path} is not JSON and PyYAML is not installed; keep agents.yml JSON-compatible"
            ) from exc
        data = yaml.safe_load(text)
        if not isinstance(data, dict):
            raise RunnerError(f"{path} must contain a mapping")
        return data


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            result[key] = "[REDACTED]" if SECRET_KEY_RE.search(str(key)) else redact(item)
        return result
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return SECRET_ASSIGNMENT_RE.sub(r"\1=[REDACTED]", value)
    return value


def ensure_no_secret_prompt(prompt: str) -> None:
    if SECRET_ASSIGNMENT_RE.search(prompt):
        raise RunnerError("Prompt appears to contain a secret assignment; refusing to run")


def normalize_task_id(task_id: str | None) -> str:
    if task_id:
        safe = re.sub(r"[^a-zA-Z0-9_.-]+", "-", task_id).strip("-")
        if safe:
            return safe[:80]
    return f"task-{int(time.time())}"


def resolve_local_path(path: str, base: Path = PROJECT_DIR) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = base / candidate
    return candidate.resolve()


def path_is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def validate_allowed_paths(allowed_paths: list[str]) -> None:
    if not allowed_paths:
        raise RunnerError("allowed_paths must not be empty")
    for item in allowed_paths:
        if not isinstance(item, str) or not item.strip():
            raise RunnerError("allowed_paths entries must be non-empty strings")
        parts = Path(item)
        if ".." in parts.parts:
            raise RunnerError(f"allowed_paths entry must not contain '..': {item}")
        if any(part in {".env", ".ssh", ".mimocode", "auth.json"} for part in parts.parts):
            raise RunnerError(f"allowed_paths entry targets forbidden secret area: {item}")


def default_quality_contract(prompt: str, task_type: str | None, mode: str) -> dict[str, Any]:
    task_label = task_type or mode or "agent-task"
    return {
        "objective": f"Complete the bounded Kolibri {task_label} assignment with a reviewable structured result.",
        "context": "This task is executed by a Mimo agent under Codex orchestration for the Kolibri AI platform.",
        "scope": [
            "Use only the provided prompt, worktree, and allowed_paths.",
            "Prefer small, inspectable findings or changes over broad refactors.",
            "Return evidence for every claim that affects merge, deploy, or server health decisions.",
        ],
        "out_of_scope": [
            "Do not read or write secrets, auth files, .env files, .ssh, or .mimocode.",
            "Do not deploy, reboot, restart services, or change firewall rules unless the manifest explicitly says so.",
            "Do not modify unrelated files or pursue speculative cleanup.",
        ],
        "acceptance_criteria": [
            "The final response includes status, summary, changed_files, checks, risks, and artifacts.",
            "Every recommendation is tied to observed evidence or an explicitly marked assumption.",
        ],
        "verification_steps": [
            "Run the manifest required_checks when available.",
            "If a check cannot run, report the blocker and exact reason.",
        ],
        "deliverables": [
            "Concise structured result JSON-compatible summary.",
            "List of changed files or an explicit empty list.",
            "Risks, blockers, and next recommended action.",
        ],
        "stop_conditions": [
            "Stop immediately if the task requires secrets or credentials not already available through safe runtime context.",
            "Stop immediately if the work requires writing outside allowed_paths.",
        ],
    }


def validate_quality_contract(contract: Any, mode: str, required_checks: list[str]) -> list[str]:
    errors: list[str] = []
    if not isinstance(contract, dict):
        return ["quality_contract must be object"]

    for field in {"objective", "context"}:
        value = contract.get(field)
        if not isinstance(value, str) or len(value.strip()) < 20:
            errors.append(f"quality_contract.{field} must be a descriptive string")
        elif SECRET_ASSIGNMENT_RE.search(value):
            errors.append(f"quality_contract.{field} appears to contain a secret assignment")

    for field in QUALITY_LIST_FIELDS:
        value = contract.get(field)
        if not isinstance(value, list) or not value:
            errors.append(f"quality_contract.{field} must be a non-empty list")
            continue
        for index, item in enumerate(value):
            if not isinstance(item, str) or len(item.strip()) < 3:
                errors.append(f"quality_contract.{field}[{index}] must be a non-empty string")
            elif SECRET_ASSIGNMENT_RE.search(item):
                errors.append(f"quality_contract.{field}[{index}] appears to contain a secret assignment")

    if mode == "controlled_mutation" and not required_checks:
        errors.append("controlled_mutation tasks must define required_checks")

    stop_text = " ".join(str(item).lower() for item in contract.get("stop_conditions", []))
    if "secret" not in stop_text and "credential" not in stop_text:
        errors.append("quality_contract.stop_conditions must include a secret/credential stop rule")

    return errors


def format_bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def prompt_for_agent(manifest: dict[str, Any]) -> str:
    contract = manifest["quality_contract"]
    required_checks = manifest.get("required_checks") or []
    checks_text = format_bullets(required_checks) if required_checks else "- No automated checks declared; explain why and provide manual verification evidence."
    budget = manifest.get("budget") or {}
    budget_text = json.dumps(redact(budget), ensure_ascii=True) if budget else "No explicit token/cost budget declared."
    return (
        "You are a Kolibri agent working under Codex review.\n\n"
        f"Agent backend: {manifest.get('agent_backend', DEFAULT_AGENT_BACKEND)}\n"
        f"Agent role: {manifest.get('agent_role', 'unspecified')}\n"
        f"Server: {manifest['server']}\n"
        f"Mode: {manifest['mode']}\n"
        f"Worktree: {manifest['worktree']}\n"
        f"Allowed paths:\n{format_bullets(list(manifest['allowed_paths']))}\n\n"
        f"Budget:\n{budget_text}\n\n"
        f"Objective:\n{contract['objective']}\n\n"
        f"Context:\n{contract['context']}\n\n"
        f"Task prompt:\n{manifest['prompt']}\n\n"
        f"Scope:\n{format_bullets(contract['scope'])}\n\n"
        f"Out of scope:\n{format_bullets(contract['out_of_scope'])}\n\n"
        f"Acceptance criteria:\n{format_bullets(contract['acceptance_criteria'])}\n\n"
        f"Verification steps:\n{format_bullets(contract['verification_steps'])}\n\n"
        f"Required checks:\n{checks_text}\n\n"
        f"Deliverables:\n{format_bullets(contract['deliverables'])}\n\n"
        f"Stop conditions:\n{format_bullets(contract['stop_conditions'])}\n\n"
        "Return a JSON-compatible structured result with exactly these top-level fields: "
        "status, summary, changed_files, checks, risks, artifacts. "
        "Do not include secrets, tokens, passwords, private keys, or raw auth file contents."
    )


def validate_manifest(manifest: dict[str, Any], agents: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required = {
        "task_id": str,
        "server": str,
        "mode": str,
        "prompt": str,
        "worktree": str,
        "allowed_paths": list,
        "quality_contract": dict,
        "required_checks": list,
        "timeout_seconds": int,
        "secrets_policy": dict,
        "expected_output": dict,
    }

    for key, expected_type in required.items():
        if key not in manifest:
            errors.append(f"missing required field: {key}")
        elif not isinstance(manifest[key], expected_type):
            errors.append(f"{key} must be {expected_type.__name__}")

    if errors:
        return errors

    servers = agents.get("servers", {})
    if manifest["server"] not in servers and manifest["server"] not in {"local", "all"}:
        errors.append(f"unknown server: {manifest['server']}")

    if manifest["mode"] not in {"read_only", "controlled_mutation", "health", "report"}:
        errors.append("mode must be one of: read_only, controlled_mutation, health, report")

    if manifest.get("allow_unsafe_permissions") is True:
        errors.append("allow_unsafe_permissions must remain false for production tasks")

    backend = manifest.get("agent_backend", DEFAULT_AGENT_BACKEND)
    if backend not in {"mimo", "openclaw"}:
        errors.append("agent_backend must be one of: mimo, openclaw")

    try:
        validate_allowed_paths(manifest["allowed_paths"])
    except RunnerError as exc:
        errors.append(str(exc))

    if SECRET_ASSIGNMENT_RE.search(manifest["prompt"]):
        errors.append("prompt appears to contain a secret assignment")

    errors.extend(
        validate_quality_contract(
            manifest.get("quality_contract"),
            manifest["mode"],
            list(manifest.get("required_checks") or []),
        )
    )

    return errors


def manifest_from_args(args: argparse.Namespace) -> dict[str, Any]:
    prompt = args.prompt or ""
    if not prompt:
        raise RunnerError("A prompt is required when --manifest is not provided")
    server = args.server or "local"
    return {
        "task_id": normalize_task_id(args.task_id),
        "agent_role": args.task_type or "custom",
        "agent_backend": args.agent_backend,
        "server": server,
        "mode": args.mode,
        "prompt": prompt,
        "worktree": args.worktree or str(PROJECT_DIR),
        "allowed_paths": args.allowed_path or ["."],
        "quality_contract": default_quality_contract(prompt, args.task_type, args.mode),
        "required_checks": args.required_check or [],
        "timeout_seconds": args.timeout,
        "secrets_policy": {
            "allow_env_files": False,
            "allow_auth_files": False,
            "redact_logs": True,
        },
        "expected_output": {
            "format": "structured_result",
            "requires_summary": True,
        },
        "openclaw_agent": args.openclaw_agent,
        "allow_unsafe_permissions": False,
    }


def load_manifest(args: argparse.Namespace) -> dict[str, Any]:
    if args.manifest:
        return load_json(resolve_local_path(args.manifest))
    return manifest_from_args(args)


def server_config(agents: dict[str, Any], server: str) -> dict[str, Any]:
    if server == "local":
        return {}
    servers = agents.get("servers", {})
    if server not in servers:
        raise RunnerError(f"Unknown server: {server}")
    config = servers[server]
    if not config.get("enabled", True):
        raise RunnerError(f"Server is disabled in ops/agents.yml: {server}")
    return config


def build_agent_argv(binary: str, manifest: dict[str, Any]) -> list[str]:
    backend = manifest.get("agent_backend", DEFAULT_AGENT_BACKEND)
    if backend == "mimo":
        return [
            binary,
            "run",
            "--format",
            "json",
            "--dir",
            str(manifest["worktree"]),
            "--model",
            manifest.get("model", DEFAULT_MODEL),
            prompt_for_agent(manifest),
        ]
    if backend == "openclaw":
        args = [
            binary,
            "agent",
            "--agent",
            manifest.get("openclaw_agent") or "kolibri-frontend",
            "--message",
            prompt_for_agent(manifest),
            "--model",
            manifest.get("model", "xiaomi-token-plan/mimo-v2.5-pro"),
            "--local",
            "--json",
        ]
        return args
    raise RunnerError(f"Unsupported agent backend: {backend}")


def backend_binary(args: argparse.Namespace, manifest: dict[str, Any], config: dict[str, Any] | None = None) -> str:
    backend = manifest.get("agent_backend", DEFAULT_AGENT_BACKEND)
    config = config or {}
    if backend == "mimo":
        return getattr(args, "mimo_bin", None) or config.get("mimo_bin") or os.environ.get("KOLIBRI_MIMO_BIN", "mimo")
    if backend == "openclaw":
        return (
            getattr(args, "openclaw_bin", None)
            or config.get("openclaw_bin")
            or os.environ.get("KOLIBRI_OPENCLAW_BIN", "openclaw")
        )
    raise RunnerError(f"Unsupported agent backend: {backend}")


def build_mimo_argv(
    mimo_bin: str,
    manifest: dict[str, Any],
) -> list[str]:
    return [
        mimo_bin,
        "run",
        "--format",
        "json",
        "--dir",
        str(manifest["worktree"]),
        "--model",
        manifest.get("model", DEFAULT_MODEL),
        prompt_for_agent(manifest),
    ]


def summarize_output(stdout: str, stderr: str) -> str:
    text = (stdout or stderr or "").strip()
    if not text:
        return "No output"
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    return first_line[:240] if first_line else "No output"


def changed_files_for(worktree: str) -> list[str]:
    path = resolve_local_path(worktree)
    if not (path / ".git").exists() and not path_is_within(path, PROJECT_DIR):
        return []
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "status", "--short"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except Exception:
        return []
    files: list[str] = []
    for line in result.stdout.splitlines():
        if len(line) > 3:
            files.append(line[3:].strip())
    return files


def run_required_checks(worktree: str, checks: list[str], timeout: int = 300) -> list[dict[str, Any]]:
    worktree_path = resolve_local_path(worktree)
    results: list[dict[str, Any]] = []
    for check in checks:
        started_at = utc_now()
        try:
            argv = shlex.split(check)
            if not argv:
                raise ValueError("empty check command")
            proc = subprocess.run(
                argv,
                cwd=str(worktree_path),
                shell=False,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            results.append(
                {
                    "command": check,
                    "status": "passed" if proc.returncode == 0 else "failed",
                    "returncode": proc.returncode,
                    "stdout": proc.stdout[-4000:],
                    "stderr": proc.stderr[-4000:],
                    "started_at": started_at,
                    "completed_at": utc_now(),
                }
            )
        except subprocess.TimeoutExpired as exc:
            results.append(
                {
                    "command": check,
                    "status": "timeout",
                    "stdout": (exc.stdout or "")[-4000:],
                    "stderr": (exc.stderr or "")[-4000:],
                    "started_at": started_at,
                    "completed_at": utc_now(),
                }
            )
        except Exception as exc:
            results.append(
                {
                    "command": check,
                    "status": "failed",
                    "stdout": "",
                    "stderr": str(exc),
                    "started_at": started_at,
                    "completed_at": utc_now(),
                }
            )
    return results


def merge_check_status(result: dict[str, Any], checks: list[dict[str, Any]]) -> None:
    result["checks"] = checks
    failed = [check for check in checks if check.get("status") != "passed"]
    if failed:
        result["status"] = "failed"
        result["risks"] = list(result.get("risks") or [])
        result["risks"].append("required_checks_failed")
        result["summary"] = f"{len(failed)} required check(s) failed"


def write_result(log_dir: Path, task_id: str, result: dict[str, Any]) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"{normalize_task_id(task_id)}-{int(time.time())}.json"
    path.write_text(json.dumps(redact(result), ensure_ascii=True, indent=2), encoding="utf-8")
    return path


def run_local(args: argparse.Namespace) -> int:
    agents = load_agents(resolve_local_path(args.agents_file))
    manifest = load_manifest(args)
    errors = validate_manifest(manifest, agents)
    if errors:
        raise RunnerError("Manifest validation failed: " + "; ".join(errors))

    ensure_no_secret_prompt(manifest["prompt"])
    ensure_no_secret_prompt(prompt_for_agent(manifest))
    worktree = resolve_local_path(manifest["worktree"])
    if not path_is_within(worktree, PROJECT_DIR):
        raise RunnerError(f"Local worktree must be inside project: {worktree}")
    if not worktree.exists():
        raise RunnerError(f"Local worktree does not exist: {worktree}")

    manifest["worktree"] = str(worktree)
    argv = build_agent_argv(backend_binary(args, manifest), manifest)
    started_at = utc_now()
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=manifest["timeout_seconds"],
            check=False,
        )
        status = "completed" if proc.returncode == 0 else "failed"
        result = {
            "task_id": manifest["task_id"],
            "server": "local",
            "status": status,
            "summary": summarize_output(proc.stdout, proc.stderr),
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "changed_files": changed_files_for(str(worktree)),
            "checks": [],
            "risks": [],
            "artifacts": [],
            "started_at": started_at,
            "completed_at": utc_now(),
        }
    except subprocess.TimeoutExpired as exc:
        result = {
            "task_id": manifest["task_id"],
            "server": "local",
            "status": "timeout",
            "summary": "Agent task timed out",
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
            "changed_files": changed_files_for(str(worktree)),
            "checks": [],
            "risks": ["timeout"],
            "artifacts": [],
            "started_at": started_at,
            "completed_at": utc_now(),
        }

    checks = run_required_checks(
        str(worktree),
        list(manifest.get("required_checks") or []),
        timeout=min(max(manifest["timeout_seconds"], 30), 900),
    )
    merge_check_status(result, checks)

    log_path = write_result(resolve_local_path(args.log_dir), manifest["task_id"], result)
    print(json.dumps({"log": str(log_path), **redact(result)}, ensure_ascii=True, indent=2))
    return 0 if result["status"] == "completed" else 1


REMOTE_LAUNCHER = r"""
import json
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime, timezone

payload = json.load(sys.stdin)
started_at = datetime.now(timezone.utc).isoformat()


SAFE_ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


def load_runtime_env(payload):
    env = os.environ.copy()
    for env_file in payload.get("runtime_env_files", []):
        with open(env_file, "r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[len("export "):].strip()
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                if not SAFE_ENV_NAME_RE.fullmatch(key):
                    continue
                if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                    value = value[1:-1]
                env[key] = value
    return env


runtime_env = load_runtime_env(payload)
if payload.get("agent_backend", "mimo") == "openclaw":
    argv = [
        payload["agent_bin"],
        "agent",
        "--agent",
        payload.get("openclaw_agent") or "kolibri-frontend",
        "--message",
        payload["prompt"],
        "--model",
        payload["model"],
        "--local",
        "--json",
    ]
else:
    argv = [
        payload["agent_bin"],
        "run",
        "--format",
        "json",
        "--dir",
        payload["worktree"],
        "--model",
        payload["model"],
        payload["prompt"],
    ]
try:
    proc = subprocess.run(
        argv,
        cwd=payload["worktree"],
        env=runtime_env,
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
        "stdout": exc.stdout or "",
        "stderr": exc.stderr or "",
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
        "summary": "Agent binary not found",
        "stdout": "",
        "stderr": "Agent binary not found: " + payload["agent_bin"],
        "changed_files": [],
        "checks": [],
        "risks": ["agent_binary_not_found"],
        "artifacts": [],
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }

checks = []
for check in payload.get("required_checks", []):
    check_started = datetime.now(timezone.utc).isoformat()
    try:
        check_proc = subprocess.run(
            shlex.split(check),
            cwd=payload["worktree"],
            env=runtime_env,
            shell=False,
            capture_output=True,
            text=True,
            timeout=min(max(payload["timeout_seconds"], 30), 900),
            check=False,
        )
        checks.append({
            "command": check,
            "status": "passed" if check_proc.returncode == 0 else "failed",
            "returncode": check_proc.returncode,
            "stdout": check_proc.stdout[-4000:],
            "stderr": check_proc.stderr[-4000:],
            "started_at": check_started,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })
    except subprocess.TimeoutExpired as exc:
        checks.append({
            "command": check,
            "status": "timeout",
            "stdout": (exc.stdout or "")[-4000:],
            "stderr": (exc.stderr or "")[-4000:],
            "started_at": check_started,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as exc:
        checks.append({
            "command": check,
            "status": "failed",
            "stdout": "",
            "stderr": str(exc),
            "started_at": check_started,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })

failed_checks = [check for check in checks if check.get("status") != "passed"]
result["checks"] = checks
if failed_checks:
    result["status"] = "failed"
    result["summary"] = str(len(failed_checks)) + " required check(s) failed"
    result.setdefault("risks", []).append("required_checks_failed")
print(json.dumps(result))
"""


def run_ssh(args: argparse.Namespace) -> int:
    agents = load_agents(resolve_local_path(args.agents_file))
    manifest = load_manifest(args)
    errors = validate_manifest(manifest, agents)
    if errors:
        raise RunnerError("Manifest validation failed: " + "; ".join(errors))
    ensure_no_secret_prompt(manifest["prompt"])
    ensure_no_secret_prompt(prompt_for_agent(manifest))

    server = manifest["server"]
    config = server_config(agents, server)
    ssh_alias = config.get("ssh_alias")
    if not ssh_alias:
        raise RunnerError(f"Server has no ssh_alias: {server}")

    payload = {
        "task_id": manifest["task_id"],
        "server": server,
        "agent_backend": manifest.get("agent_backend", DEFAULT_AGENT_BACKEND),
        "agent_bin": backend_binary(args, manifest, config),
        "openclaw_agent": manifest.get("openclaw_agent") or config.get("openclaw_agent") or "kolibri-frontend",
        "worktree": manifest["worktree"],
        "model": manifest.get("model", DEFAULT_MODEL),
        "prompt": prompt_for_agent(manifest),
        "timeout_seconds": manifest["timeout_seconds"],
        "required_checks": manifest.get("required_checks") or [],
        "runtime_env_files": config.get("runtime_env_files") or [],
    }

    ssh_cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]
    if config.get("ssh_port"):
        ssh_cmd.extend(["-p", str(config["ssh_port"])])
    ssh_cmd.extend([ssh_alias, "python3 -c " + shlex.quote(REMOTE_LAUNCHER)])

    try:
        proc = subprocess.run(
            ssh_cmd,
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=manifest["timeout_seconds"] + 30,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        result = {
            "task_id": manifest["task_id"],
            "server": server,
            "status": "timeout",
            "summary": "SSH task timed out",
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
            "changed_files": [],
            "checks": [],
            "risks": ["ssh_timeout"],
            "artifacts": [],
            "started_at": utc_now(),
            "completed_at": utc_now(),
        }
    else:
        if proc.returncode == 0:
            try:
                result = json.loads(proc.stdout)
            except json.JSONDecodeError:
                result = {
                    "task_id": manifest["task_id"],
                    "server": server,
                    "status": "failed",
                    "summary": "Remote runner returned non-JSON output",
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                    "changed_files": [],
                    "checks": [],
                    "risks": ["invalid_remote_output"],
                    "artifacts": [],
                    "started_at": utc_now(),
                    "completed_at": utc_now(),
                }
        else:
            result = {
                "task_id": manifest["task_id"],
                "server": server,
                "status": "failed",
                "summary": summarize_output(proc.stdout, proc.stderr),
                "returncode": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "changed_files": [],
                "checks": [],
                "risks": ["ssh_failed"],
                "artifacts": [],
                "started_at": utc_now(),
                "completed_at": utc_now(),
            }

    log_path = write_result(resolve_local_path(args.log_dir), manifest["task_id"], result)
    print(json.dumps({"log": str(log_path), **redact(result)}, ensure_ascii=True, indent=2))
    return 0 if result["status"] == "completed" else 1


def validate_command(args: argparse.Namespace) -> int:
    agents = load_agents(resolve_local_path(args.agents_file))
    manifest = load_manifest(args)
    errors = validate_manifest(manifest, agents)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"status": "valid", "task_id": manifest["task_id"]}, indent=2))
    return 0


def collect(args: argparse.Namespace) -> int:
    log_dir = resolve_local_path(args.log_dir)
    results = []
    for path in sorted(log_dir.glob("*.json"), reverse=True)[: args.limit]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if args.status != "all" and data.get("status") != args.status:
            continue
        results.append({"file": str(path), **data})
    print(json.dumps({"count": len(results), "results": redact(results)}, indent=2))
    return 0


def report(args: argparse.Namespace) -> int:
    log_dir = resolve_local_path(args.log_dir)
    cutoff = time.time() - args.hours * 3600
    results = []
    for path in log_dir.glob("*.json"):
        if path.stat().st_mtime < cutoff:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        results.append(data)

    by_status: dict[str, int] = {}
    by_server: dict[str, int] = {}
    failures = []
    changed_files: set[str] = set()
    for item in results:
        status = item.get("status", "unknown")
        server = item.get("server", "unknown")
        by_status[status] = by_status.get(status, 0) + 1
        by_server[server] = by_server.get(server, 0) + 1
        changed_files.update(item.get("changed_files") or [])
        if status not in {"completed"}:
            failures.append(
                {
                    "task_id": item.get("task_id"),
                    "server": server,
                    "status": status,
                    "summary": item.get("summary"),
                }
            )

    payload = {
        "status": "ok",
        "window_hours": args.hours,
        "total_tasks": len(results),
        "by_status": by_status,
        "by_server": by_server,
        "failures": failures[:10],
        "changed_files": sorted(changed_files)[:50],
        "generated_at": utc_now(),
    }
    print(json.dumps(redact(payload), indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Safe Kolibri Mimo/OpenClaw task runner")
    parser.add_argument("--agents-file", default=str(DEFAULT_AGENTS_FILE))
    parser.add_argument("--log-dir", default=str(DEFAULT_LOG_DIR))
    sub = parser.add_subparsers(dest="command", required=True)

    def add_task_args(command: argparse.ArgumentParser) -> None:
        command.add_argument("--manifest")
        command.add_argument("--server")
        command.add_argument("--prompt")
        command.add_argument("--task-id")
        command.add_argument("--task-type")
        command.add_argument("--agent-backend", choices=["mimo", "openclaw"], default=DEFAULT_AGENT_BACKEND)
        command.add_argument("--openclaw-agent", default="kolibri-frontend")
        command.add_argument("--mode", default="read_only")
        command.add_argument("--worktree", default=str(PROJECT_DIR))
        command.add_argument("--allowed-path", action="append")
        command.add_argument("--required-check", action="append")
        command.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)

    validate_p = sub.add_parser("validate", help="Validate a task manifest")
    add_task_args(validate_p)
    validate_p.set_defaults(func=validate_command)

    local_p = sub.add_parser("run-local", help="Run an agent locally through argv")
    add_task_args(local_p)
    local_p.add_argument("--mimo-bin")
    local_p.add_argument("--openclaw-bin")
    local_p.set_defaults(func=run_local)

    ssh_p = sub.add_parser("run-ssh", help="Run an agent on a remote server through SSH stdin")
    add_task_args(ssh_p)
    ssh_p.add_argument("--mimo-bin")
    ssh_p.add_argument("--openclaw-bin")
    ssh_p.set_defaults(func=run_ssh)

    collect_p = sub.add_parser("collect", help="Collect task run logs")
    collect_p.add_argument("--status", default="all")
    collect_p.add_argument("--limit", type=int, default=20)
    collect_p.set_defaults(func=collect)

    report_p = sub.add_parser("report", help="Summarize recent task run logs")
    report_p.add_argument("--hours", type=int, default=12)
    report_p.set_defaults(func=report)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except RunnerError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
