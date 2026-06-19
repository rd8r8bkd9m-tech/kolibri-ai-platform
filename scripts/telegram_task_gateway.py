#!/usr/bin/env python3
"""Telegram intake gateway for safe Kolibri Mimo task manifests.

The gateway is intentionally an intake layer only:
- Telegram access is restricted by an allowlist of user IDs from env.
- /submit writes a bounded task manifest and validates it through
  scripts/mimo_task_runner.py using subprocess argv, never shell=True.
- It never starts Mimo, SSH, deploys, browsers, paid APIs, or arbitrary shell.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RUNNER = PROJECT_DIR / "scripts" / "mimo_task_runner.py"
DEFAULT_QUEUE_DIR = PROJECT_DIR / "ops" / "tasks" / "telegram-queue"
DEFAULT_LOG_DIR = PROJECT_DIR / "logs" / "agent-runs"
DEFAULT_MAX_TASK_CHARS = 3000
SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b([A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|PASSWD|API_KEY|PRIVATE_KEY)[A-Z0-9_]*)\s*=\s*([^\s]+)"
)


class GatewayError(RuntimeError):
    """User-facing gateway failure."""


@dataclass(frozen=True)
class GatewayConfig:
    bot_token: str
    allowed_user_ids: set[int]
    queue_dir: Path
    log_dir: Path
    runner_path: Path
    default_server: str
    default_worktree: str
    readonly_allowed_paths: list[str]
    controlled_allowed_paths: list[str]
    controlled_required_checks: list[str]
    max_task_chars: int


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def env_list(name: str, default: str = "") -> list[str]:
    value = os.environ.get(name, default)
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_user_ids(value: str) -> set[int]:
    user_ids: set[int] = set()
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        if not item.isdigit():
            raise GatewayError(f"Invalid Telegram user ID in allowlist: {item}")
        user_ids.add(int(item))
    return user_ids


def load_config(require_token: bool = False) -> GatewayConfig:
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if require_token and not bot_token:
        raise GatewayError("TELEGRAM_BOT_TOKEN is required to run the Telegram poller")

    allowed_raw = os.environ.get(
        "KOLIBRI_TELEGRAM_ALLOWED_USER_IDS",
        os.environ.get("TELEGRAM_ALLOWED_USER_IDS", ""),
    )
    allowed_user_ids = parse_user_ids(allowed_raw)
    if not allowed_user_ids:
        raise GatewayError("KOLIBRI_TELEGRAM_ALLOWED_USER_IDS must contain at least one user ID")

    try:
        max_task_chars = int(os.environ.get("KOLIBRI_TELEGRAM_MAX_TASK_CHARS", DEFAULT_MAX_TASK_CHARS))
    except ValueError as exc:
        raise GatewayError("KOLIBRI_TELEGRAM_MAX_TASK_CHARS must be an integer") from exc
    if max_task_chars < 100:
        raise GatewayError("KOLIBRI_TELEGRAM_MAX_TASK_CHARS must be at least 100")

    return GatewayConfig(
        bot_token=bot_token,
        allowed_user_ids=allowed_user_ids,
        queue_dir=resolve_path(os.environ.get("KOLIBRI_TELEGRAM_QUEUE_DIR", str(DEFAULT_QUEUE_DIR))),
        log_dir=resolve_path(os.environ.get("KOLIBRI_TELEGRAM_LOG_DIR", str(DEFAULT_LOG_DIR))),
        runner_path=resolve_path(os.environ.get("KOLIBRI_TELEGRAM_RUNNER", str(DEFAULT_RUNNER))),
        default_server=os.environ.get("KOLIBRI_TELEGRAM_DEFAULT_SERVER", "local"),
        default_worktree=os.environ.get("KOLIBRI_TELEGRAM_DEFAULT_WORKTREE", "."),
        readonly_allowed_paths=env_list("KOLIBRI_TELEGRAM_READONLY_ALLOWED_PATHS", "."),
        controlled_allowed_paths=env_list("KOLIBRI_TELEGRAM_CONTROLLED_ALLOWED_PATHS", "docs,scripts,ops/tasks"),
        controlled_required_checks=env_list(
            "KOLIBRI_TELEGRAM_CONTROLLED_REQUIRED_CHECKS",
            "python3 -m py_compile scripts/mimo_task_runner.py scripts/telegram_task_gateway.py",
        ),
        max_task_chars=max_task_chars,
    )


def resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_DIR / path
    return path.resolve()


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_DIR))
    except ValueError:
        return str(path)


def redact_text(text: str, token: str = "") -> str:
    redacted = SECRET_ASSIGNMENT_RE.sub(r"\1=[REDACTED]", text)
    if token:
        redacted = redacted.replace(token, "[REDACTED_TOKEN]")
    return redacted


def structured(
    status: str,
    summary: str,
    *,
    changed_files: list[str] | None = None,
    checks: list[dict[str, Any]] | None = None,
    risks: list[str] | None = None,
    artifacts: list[str] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    payload = {
        "status": status,
        "summary": summary,
        "changed_files": changed_files or [],
        "checks": checks or [],
        "risks": risks or [],
        "artifacts": artifacts or [],
    }
    payload.update(extra)
    return payload


def command_name(text: str) -> tuple[str, str]:
    stripped = text.strip()
    if not stripped:
        return "", ""
    first, _, rest = stripped.partition(" ")
    command = first.split("@", 1)[0].lower()
    return command, rest.strip()


def ensure_authorized(user_id: int, config: GatewayConfig) -> None:
    if user_id not in config.allowed_user_ids:
        raise GatewayError("Telegram user is not in the allowlist")


def ensure_safe_task_text(task_text: str, max_chars: int) -> None:
    if len(task_text.strip()) < 10:
        raise GatewayError("Task text is too short for a safe manifest")
    if len(task_text) > max_chars:
        raise GatewayError(f"Task text exceeds {max_chars} characters")
    if SECRET_ASSIGNMENT_RE.search(task_text):
        raise GatewayError("Task text appears to contain a secret assignment; refusing to store it")


def make_task_id(task_text: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    digest = hashlib.sha256(f"{timestamp}\n{task_text}".encode("utf-8")).hexdigest()[:10]
    return f"telegram-{timestamp}-{digest}"


def quality_contract(mode: str) -> dict[str, Any]:
    if mode == "controlled_mutation":
        return {
            "objective": "Prepare a bounded controlled mutation task from Telegram for later Codex review and explicit execution.",
            "context": "The Telegram gateway is an untrusted intake boundary; this manifest must not start agents by itself.",
            "scope": [
                "Use only the submitted task text and the allowed paths declared in this manifest.",
                "Keep any future edits narrow, reviewable, and inside allowed_paths.",
                "Run required checks only when a separate runner execution is approved.",
            ],
            "out_of_scope": [
                "Do not deploy, push, merge, restart services, alter HostVDS, or touch infrastructure state.",
                "Do not read or write secrets, .env files, .ssh, .mimocode, auth files, or credentials.",
                "Do not execute this manifest automatically from Telegram intake.",
            ],
            "acceptance_criteria": [
                "Manifest validates successfully through scripts/mimo_task_runner.py validate.",
                "Controlled mutation remains queued until Codex performs an explicit separate approval step.",
                "A future result must include status, summary, changed_files, checks, risks, and artifacts.",
            ],
            "verification_steps": [
                "Validate the manifest before it enters the queue.",
                "Require a separate operator approval before any run-local or run-ssh invocation.",
            ],
            "deliverables": [
                "Queued manifest artifact for Codex review.",
                "Structured response with validation status and residual risks.",
            ],
            "stop_conditions": [
                "Stop if the task requires secrets, credentials, private keys, auth files, or environment dumps.",
                "Stop if the task requires writing outside allowed_paths or changing production state.",
            ],
        }

    return {
        "objective": "Capture a Telegram-submitted Kolibri task as a safe read-only draft for Codex review.",
        "context": "The Telegram gateway accepts untrusted human input and only validates manifests without starting Mimo.",
        "scope": [
            "Treat the submitted text as a read-only investigation or planning request.",
            "Use only allowed_paths and report evidence instead of changing repository or server state.",
            "Return recommendations for any later controlled mutation as a separate approval step.",
        ],
        "out_of_scope": [
            "Do not edit files, deploy, push, merge, restart services, browse paid systems, or contact servers.",
            "Do not read secrets, .env files, .ssh, .mimocode, auth files, tokens, or private keys.",
            "Do not execute real agents automatically from Telegram intake.",
        ],
        "acceptance_criteria": [
            "Manifest validates successfully through scripts/mimo_task_runner.py validate.",
            "No real Mimo, SSH, deployment, browser, email, or payment action is started.",
            "A future result must include status, summary, changed_files, checks, risks, and artifacts.",
        ],
        "verification_steps": [
            "Validate the manifest before it enters the queue.",
            "Report that no agent execution happened during Telegram intake.",
        ],
        "deliverables": [
            "Queued read-only manifest artifact for Codex review.",
            "Structured response with validation status and residual risks.",
        ],
        "stop_conditions": [
            "Stop if the task requires secrets, credentials, private keys, auth files, or environment dumps.",
            "Stop if the task requires modifying files or changing production/server state.",
        ],
    }


def manifest_for_submit(task_text: str, mode: str, config: GatewayConfig) -> dict[str, Any]:
    task_id = make_task_id(task_text)
    approved_note = ""
    if mode == "controlled_mutation":
        approved_note = (
            "\n\nThe Telegram command included --approve-controlled-mutation, "
            "but Codex must still review and explicitly invoke the runner before any execution."
        )

    return {
        "task_id": task_id,
        "agent_role": "Telegram Gateway Intake",
        "server": config.default_server,
        "mode": mode,
        "prompt": (
            "Telegram intake task from an allowlisted operator.\n\n"
            f"Requested task:\n{task_text.strip()}\n\n"
            "Do not start agents from this intake step. Do not use secrets. "
            "Return only a structured result if this manifest is later executed."
            f"{approved_note}"
        ),
        "worktree": config.default_worktree,
        "allowed_paths": (
            config.controlled_allowed_paths if mode == "controlled_mutation" else config.readonly_allowed_paths
        ),
        "quality_contract": quality_contract(mode),
        "required_checks": config.controlled_required_checks if mode == "controlled_mutation" else [],
        "timeout_seconds": 300,
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


def write_manifest(manifest: dict[str, Any], queue_dir: Path) -> Path:
    queue_dir.mkdir(parents=True, exist_ok=True)
    try:
        queue_dir.chmod(0o700)
    except OSError:
        pass

    path = queue_dir / f"{manifest['task_id']}.json"
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(path)
    return path


def display_command(argv: list[str]) -> str:
    parts = []
    for index, item in enumerate(argv):
        if index == 0 and Path(item) == Path(sys.executable):
            parts.append("python3")
        elif item.startswith(str(PROJECT_DIR)):
            parts.append(str(Path(item).relative_to(PROJECT_DIR)))
        else:
            parts.append(item)
    return shlex.join(parts)


def run_runner(config: GatewayConfig, args: list[str], timeout: int = 30) -> dict[str, Any]:
    argv = [
        sys.executable,
        str(config.runner_path),
        "--log-dir",
        str(config.log_dir),
        *args,
    ]
    started_at = utc_now()
    command = display_command(argv)
    try:
        proc = subprocess.run(
            argv,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "status": "timeout",
            "stdout": (exc.stdout or "")[-4000:],
            "stderr": (exc.stderr or "")[-4000:],
            "started_at": started_at,
            "completed_at": utc_now(),
        }
    except FileNotFoundError as exc:
        return {
            "command": command,
            "status": "failed",
            "returncode": None,
            "stdout": "",
            "stderr": str(exc),
            "started_at": started_at,
            "completed_at": utc_now(),
        }
    return {
        "command": command,
        "status": "passed" if proc.returncode == 0 else "failed",
        "returncode": proc.returncode,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
        "started_at": started_at,
        "completed_at": utc_now(),
    }


def validate_manifest(path: Path, config: GatewayConfig) -> dict[str, Any]:
    return run_runner(config, ["validate", "--manifest", str(path)], timeout=30)


def parse_submit_args(raw: str) -> tuple[str, str]:
    try:
        tokens = shlex.split(raw)
    except ValueError as exc:
        raise GatewayError(f"Could not parse /submit arguments: {exc}") from exc

    mode = "read_only"
    approved_controlled = False
    deploy_requested = False
    task_tokens: list[str] = []

    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            task_tokens.extend(tokens[index + 1 :])
            break
        if token in {"--controlled", "--controlled-mutation"}:
            mode = "controlled_mutation"
        elif token == "--approve-controlled-mutation":
            approved_controlled = True
        elif token in {"--deploy", "--approve-deploy"}:
            deploy_requested = True
        elif token == "--mode":
            index += 1
            if index >= len(tokens):
                raise GatewayError("--mode requires a value")
            value = tokens[index]
            if value == "read_only":
                mode = "read_only"
            elif value == "controlled_mutation":
                mode = "controlled_mutation"
            elif value == "deploy":
                deploy_requested = True
            else:
                raise GatewayError("--mode must be read_only or controlled_mutation")
        elif token.startswith("--"):
            raise GatewayError(f"Unknown /submit flag: {token}")
        else:
            task_tokens.extend(tokens[index:])
            break
        index += 1

    if deploy_requested:
        raise GatewayError("Deploy tasks are not supported by the Telegram MVP")
    if mode == "controlled_mutation" and not approved_controlled:
        raise GatewayError("controlled_mutation requires --approve-controlled-mutation")

    return mode, " ".join(task_tokens).strip()


def submit_task(raw: str, config: GatewayConfig) -> dict[str, Any]:
    mode, task_text = parse_submit_args(raw)
    ensure_safe_task_text(task_text, config.max_task_chars)

    manifest = manifest_for_submit(task_text, mode, config)
    manifest_path = write_manifest(manifest, config.queue_dir)
    check = validate_manifest(manifest_path, config)
    rel_manifest = display_path(manifest_path)

    if check["status"] != "passed":
        return structured(
            "failed",
            "Task manifest was written but failed runner validation; it must not be executed.",
            changed_files=[rel_manifest],
            checks=[check],
            risks=["manifest_validation_failed"],
            artifacts=[str(manifest_path)],
            task_id=manifest["task_id"],
            mode=mode,
        )

    risks = ["queued_only_no_agent_started"]
    if mode == "controlled_mutation":
        risks.append("requires_separate_codex_execution_approval")

    return structured(
        "queued",
        "Task manifest created and validated; no Mimo agent was started.",
        changed_files=[rel_manifest],
        checks=[check],
        risks=risks,
        artifacts=[str(manifest_path)],
        task_id=manifest["task_id"],
        mode=mode,
    )


def queue_count(queue_dir: Path) -> int:
    if not queue_dir.exists():
        return 0
    return sum(1 for path in queue_dir.glob("*.json") if path.is_file())


def status_report(config: GatewayConfig) -> dict[str, Any]:
    report_check = run_runner(config, ["report", "--hours", "12"], timeout=30)
    total_tasks = None
    by_status = {}
    if report_check["stdout"]:
        try:
            report_payload = json.loads(report_check["stdout"])
            total_tasks = report_payload.get("total_tasks")
            by_status = report_payload.get("by_status") or {}
        except json.JSONDecodeError:
            pass

    pending = queue_count(config.queue_dir)
    summary = f"Queue has {pending} manifest(s)."
    if total_tasks is not None:
        summary += f" Runner logs in the last 12h: {total_tasks} task(s)."

    risks = [] if report_check["status"] == "passed" else ["runner_report_failed"]
    return structured(
        "ok" if not risks else "degraded",
        summary,
        checks=[report_check],
        risks=risks,
        artifacts=[str(config.queue_dir), str(config.log_dir)],
        queue_count=pending,
        runner_total_tasks_12h=total_tasks,
        runner_by_status_12h=by_status,
    )


def help_report() -> dict[str, Any]:
    return structured(
        "ok",
        "Commands: /status, /submit <task>, /submit --controlled --approve-controlled-mutation <task>, /help.",
        risks=[
            "gateway_never_starts_agents",
            "deploy_tasks_rejected_in_mvp",
            "controlled_mutation_requires_separate_codex_execution_approval",
        ],
    )


def handle_text(user_id: int, text: str, config: GatewayConfig) -> dict[str, Any]:
    ensure_authorized(user_id, config)
    command, raw = command_name(text)
    if command == "/help":
        return help_report()
    if command == "/status":
        return status_report(config)
    if command == "/submit":
        return submit_task(raw, config)
    return structured(
        "rejected",
        "Unknown command. Use /help, /status, or /submit <task>.",
        risks=["unknown_command"],
    )


def json_message(payload: dict[str, Any], token: str = "") -> str:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    text = redact_text(text, token)
    if len(text) <= 3900:
        return text
    clipped = text[:3600] + "\n... [truncated]"
    return clipped


class TelegramClient:
    def __init__(self, token: str) -> None:
        self.token = token
        self.base_url = f"https://api.telegram.org/bot{token}"

    def request(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = urllib.parse.urlencode(payload).encode("utf-8")
        req = urllib.request.Request(f"{self.base_url}/{method}", data=data, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=35) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.URLError as exc:
            raise GatewayError(redact_text(f"Telegram API request failed: {exc}", self.token)) from exc

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise GatewayError("Telegram API returned invalid JSON") from exc
        if not parsed.get("ok"):
            raise GatewayError(redact_text(f"Telegram API error: {parsed}", self.token))
        return parsed

    def get_updates(self, offset: int | None) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {"timeout": 25, "allowed_updates": json.dumps(["message"])}
        if offset is not None:
            payload["offset"] = offset
        return list(self.request("getUpdates", payload).get("result") or [])

    def send_message(self, chat_id: int, text: str) -> None:
        self.request(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": text,
                "disable_web_page_preview": "true",
            },
        )


def run_polling(config: GatewayConfig) -> int:
    client = TelegramClient(config.bot_token)
    offset: int | None = None
    print("Telegram task gateway polling started", file=sys.stderr)
    while True:
        try:
            updates = client.get_updates(offset)
        except GatewayError as exc:
            print(redact_text(str(exc), config.bot_token), file=sys.stderr)
            time.sleep(5)
            continue

        for update in updates:
            offset = int(update["update_id"]) + 1
            message = update.get("message") or {}
            text = message.get("text")
            chat = message.get("chat") or {}
            sender = message.get("from") or {}
            chat_id = chat.get("id")
            user_id = sender.get("id")
            if not isinstance(text, str) or not isinstance(chat_id, int) or not isinstance(user_id, int):
                continue
            try:
                payload = handle_text(user_id, text, config)
            except GatewayError as exc:
                payload = structured(
                    "rejected",
                    str(exc),
                    risks=["request_rejected"],
                )
            except Exception as exc:  # pragma: no cover - defensive runtime boundary
                payload = structured(
                    "failed",
                    "Gateway failed while handling command.",
                    risks=[redact_text(str(exc), config.bot_token)],
                )
            client.send_message(chat_id, json_message(payload, config.bot_token))
    return 0


def handle_cli(args: argparse.Namespace) -> int:
    config = load_config(require_token=False)
    try:
        payload = handle_text(args.user_id, args.text, config)
    except GatewayError as exc:
        payload = structured("rejected", str(exc), risks=["request_rejected"])
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["status"] not in {"failed"} else 1


def self_test() -> int:
    with tempfile.TemporaryDirectory(prefix="kolibri-telegram-gateway-") as tmp:
        os.environ["KOLIBRI_TELEGRAM_ALLOWED_USER_IDS"] = "12345"
        os.environ["KOLIBRI_TELEGRAM_QUEUE_DIR"] = str(Path(tmp) / "queue")
        os.environ["KOLIBRI_TELEGRAM_LOG_DIR"] = str(Path(tmp) / "logs")
        config = load_config(require_token=False)

        results = [
            handle_text(12345, "/help", config),
            handle_text(12345, "/status", config),
            handle_text(12345, "/submit Review docs for stale Telegram gateway runbook notes", config),
        ]

        try:
            handle_text(54321, "/status", config)
        except GatewayError:
            unauthorized_ok = True
        else:
            unauthorized_ok = False

        checks = [
            {
                "name": "help",
                "status": "passed" if results[0]["status"] == "ok" else "failed",
            },
            {
                "name": "status",
                "status": "passed" if results[1]["status"] in {"ok", "degraded"} else "failed",
            },
            {
                "name": "submit_validate",
                "status": "passed" if results[2]["status"] == "queued" else "failed",
            },
            {
                "name": "allowlist_rejects_unknown_user",
                "status": "passed" if unauthorized_ok else "failed",
            },
        ]
        failed = [check for check in checks if check["status"] != "passed"]
        payload = structured(
            "passed" if not failed else "failed",
            "Telegram gateway self-test completed.",
            checks=checks,
            risks=[] if not failed else ["self_test_failed"],
            artifacts=[str(config.queue_dir)],
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if not failed else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Safe Telegram task gateway for Kolibri manifests")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Run Telegram long polling")
    run_p.set_defaults(func=lambda _args: run_polling(load_config(require_token=True)))

    handle_p = sub.add_parser("handle", help="Handle one command without Telegram network access")
    handle_p.add_argument("--user-id", type=int, required=True)
    handle_p.add_argument("--text", required=True)
    handle_p.set_defaults(func=handle_cli)

    self_p = sub.add_parser("self-test", help="Run local smoke checks without Telegram or Mimo")
    self_p.set_defaults(func=lambda _args: self_test())

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except GatewayError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
