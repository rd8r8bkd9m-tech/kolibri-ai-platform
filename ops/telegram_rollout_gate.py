#!/usr/bin/env python3
"""Executable rollout gate for the Telegram readable formatter."""

from __future__ import annotations

import argparse
import importlib.util
import io
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = ROOT / "docs/agent-work/generated/remote-server-transfer-20260629T1603/telegram-live-verification-main.md"
DEFAULT_TASK_ID = "KOL-REMOTE-SERVER-TASK-20260629T1603-002B-MAIN-TELEGRAM-IMPLEMENTATION"
CHANGED_FILES = [
    "ops/telegram_gateway.py",
    "ops/telegram_rollout_gate.py",
    "tests/test_telegram_gateway.py",
    "docs/agent-work/generated/remote-server-transfer-20260629T1603/telegram-live-verification-main.md",
]
VERIFICATION_COMMANDS = [
    ["python3", "-m", "compileall", "-q", "ops", "tests"],
    ["python3", "-m", "pytest", "-q", "tests/test_telegram_gateway.py", "tests/test_agent_host_telegram_chat.py"],
]
DELIVERABLE_COMMANDS = [
    ["git", "diff", "--check"],
    ["git", "status", "--short"],
    ["test", "-f", "docs/agent-work/generated/remote-server-transfer-20260629T1603/telegram-live-verification-main.md"],
]
ROLLBACK_COMMANDS = [
    "sudo systemctl stop kolibri-telegram-gateway.service",
    "cd /opt/kolibri-ai-platform && sudo git checkout HEAD~1 -- ops/telegram_gateway.py",
    "sudo install -m 0755 /opt/kolibri-ai-platform/ops/telegram_gateway.py /usr/local/bin/kolibri-telegram-gateway",
    "sudo systemctl start kolibri-telegram-gateway.service",
    "sudo journalctl -u kolibri-telegram-gateway.service -n 80 --no-pager",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_gateway() -> Any:
    spec = importlib.util.spec_from_file_location("telegram_gateway", ROOT / "ops/telegram_gateway.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def run_check(name: str, check: Callable[[Any], dict[str, Any]]) -> dict[str, Any]:
    gateway = load_gateway()
    started = utc_now()
    try:
        detail = check(gateway)
        return {"name": name, "status": "PASS", "started_at": started, "finished_at": utc_now(), "detail": detail}
    except Exception as exc:
        return {
            "name": name,
            "status": "FAIL",
            "started_at": started,
            "finished_at": utc_now(),
            "error": f"{type(exc).__name__}: {exc}",
        }


def check_no_raw_json(gateway: Any) -> dict[str, Any]:
    payload = json.dumps(
        {
            "task_id": "TGCHAT-202606291603-1-chat",
            "node_id": "primary-candidate",
            "result_path": "/var/lib/kolibri-agent/artifacts/result.json",
            "response": "Готово <b>безопасно</b> & понятно.",
        },
        ensure_ascii=False,
    )
    task = {"state": "completed", "result": {"response": payload}}
    message = gateway.format_transition("COMPLETED", task, mode="chat")
    forbidden = ["{", "}", "task_id", "node_id", "result_path", "/var/lib"]
    leaked = [marker for marker in forbidden if marker in message]
    if leaked:
        raise AssertionError(f"formatter leaked raw markers: {leaked}")
    return {"formatted_message": message}


def check_html_escaping(gateway: Any) -> dict[str, Any]:
    calls: list[dict[str, list[str]]] = []

    class Response:
        status = 200

        def __enter__(self) -> "Response":
            return self

        def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
            return False

        def read(self) -> bytes:
            return b'{"ok":true,"result":{"message_id":1}}'

    def fake_urlopen(req: urllib.request.Request, timeout: int = 35) -> Response:
        del timeout
        calls.append(urllib.parse.parse_qs((req.data or b"").decode("utf-8")))
        return Response()

    original_urlopen = gateway.urllib.request.urlopen
    gateway.urllib.request.urlopen = fake_urlopen
    try:
        client = gateway.TelegramClient("000:rollout-gate", api_base="https://telegram.invalid")
        client.send_message(100, "5 < 7 & <b>raw</b>")
    finally:
        gateway.urllib.request.urlopen = original_urlopen
    payload = calls[0]
    expected = "5 &lt; 7 &amp; &lt;b&gt;raw&lt;/b&gt;"
    if payload.get("text") != [expected] or payload.get("parse_mode") != ["HTML"]:
        raise AssertionError(f"unexpected Telegram payload: {payload}")
    return {"parse_mode": "HTML", "escaped_text": expected}


def check_getupdates_409_ownership(gateway: Any) -> dict[str, Any]:
    def fake_urlopen(req: urllib.request.Request, timeout: int = 35) -> Any:
        del timeout
        raise urllib.error.HTTPError(
            req.full_url,
            409,
            "Conflict",
            {},
            io.BytesIO(b'{"ok":false,"error_code":409,"description":"terminated by other getUpdates request"}'),
        )

    original_urlopen = gateway.urllib.request.urlopen
    gateway.urllib.request.urlopen = fake_urlopen
    try:
        client = gateway.TelegramClient("000:rollout-gate", api_base="https://telegram.invalid")
        try:
            client.get_updates(None, 1)
        except gateway.TelegramPollOwnershipError as exc:
            return {"ownership_error": str(exc)}
    finally:
        gateway.urllib.request.urlopen = original_urlopen
    raise AssertionError("getUpdates 409 did not raise TelegramPollOwnershipError")


def check_rollback_contract(_: Any) -> dict[str, Any]:
    service_path = ROOT / "ops/systemd/kolibri-telegram-gateway.service"
    if not service_path.exists():
        raise AssertionError(f"missing service unit: {service_path.relative_to(ROOT)}")
    return {"service_unit": str(service_path.relative_to(ROOT)), "rollback_commands": ROLLBACK_COMMANDS}


def run_command_list(commands: list[list[str]]) -> list[dict[str, Any]]:
    results = []
    for command in commands:
        started = utc_now()
        proc = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
        results.append(
            {
                "command": " ".join(command),
                "status": "PASS" if proc.returncode == 0 else "FAIL",
                "returncode": proc.returncode,
                "started_at": started,
                "finished_at": utc_now(),
                "stdout_tail": proc.stdout.strip()[-2000:],
                "stderr_tail": proc.stderr.strip()[-2000:],
            }
        )
    return results


def run_verification_commands() -> list[dict[str, Any]]:
    return run_command_list(VERIFICATION_COMMANDS)


def run_deliverable_commands() -> list[dict[str, Any]]:
    return run_command_list(DELIVERABLE_COMMANDS)


def live_telegram_probe(enabled: bool) -> dict[str, Any]:
    if not enabled:
        return {
            "status": "FALLBACK",
            "reason": "live Telegram probe not requested",
            "agent_message": "Telegram live access was not used; offline formatter and ownership gates are recorded in this report.",
        }
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        return {
            "status": "FALLBACK",
            "reason": "TELEGRAM_BOT_TOKEN is not set",
            "agent_message": "Telegram is unavailable in this environment; use this artifact as the fallback agent-message/report.",
        }
    gateway = load_gateway()
    try:
        result = gateway.TelegramClient(token).call("getMe", {}, timeout=10).get("result") or {}
        return {"status": "PASS", "bot_id": result.get("id"), "username": result.get("username")}
    except Exception as exc:
        return {
            "status": "FALLBACK",
            "reason": f"{type(exc).__name__}: {exc}",
            "agent_message": "Telegram live check failed; offline gate results and rollback steps are preserved in this report.",
        }


def annotate_control_plane(control_url: str, task_id: str, report_path: Path, status: str, command_results: list[dict[str, Any]]) -> dict[str, Any]:
    if not task_id:
        return {"status": "SKIPPED", "reason": "task id not provided"}
    commands = [item["command"] for item in command_results]
    body = {
        "result_reference": str(report_path),
        "result": {
            "status": "completed" if status == "PASS" else "failed",
            "kind": "telegram_rollout_gate",
            "report_path": str(report_path),
            "result_path": str(report_path),
            "changed_files": CHANGED_FILES,
            "verification_commands": commands,
            "telegram_rollout_gate": {
                "status": status,
                "report_path": str(report_path),
                "generated_at": utc_now(),
            }
        },
    }
    url = f"{control_url.rstrip('/')}/v1/tasks/{urllib.parse.quote(task_id, safe='')}/annotate"
    req = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = resp.read().decode("utf-8")
            return {"status": "PASS", "http_status": resp.status, "response": json.loads(payload) if payload else {}}
    except Exception as exc:
        return {"status": "FALLBACK", "reason": f"{type(exc).__name__}: {exc}", "result_reference": str(report_path)}


def command_line(args: argparse.Namespace) -> str:
    path = args.report
    try:
        path = str(Path(path).resolve().relative_to(ROOT))
    except ValueError:
        path = str(path)
    parts = ["python3", "ops/telegram_rollout_gate.py", "--report", path, "--task-id", args.task_id]
    if args.live_telegram:
        parts.append("--live-telegram")
    return " ".join(parts)


def markdown_report(data: dict[str, Any]) -> str:
    lines = [
        "# Telegram Live Verification Main",
        "",
        f"- generated_at: `{data['generated_at']}`",
        f"- status: `{data['status']}`",
        f"- task_id: `{data['task_id']}`",
        f"- result_reference: `{data['result_reference']}`",
        "",
        "## Verification Commands",
        "",
        f"- `{data['gate_command']}`",
    ]
    for result in data["verification_commands"]:
        lines.append(f"- `{result['command']}` -> `{result['status']}` rc={result['returncode']}")
    lines.extend(["", "## Gate Checks", ""])
    for check in data["checks"]:
        lines.append(f"- `{check['name']}`: `{check['status']}`")
        if check.get("error"):
            lines.append(f"  - error: `{check['error']}`")
        elif check.get("detail", {}).get("formatted_message"):
            lines.append(f"  - formatted_message: {check['detail']['formatted_message']}")
        elif check.get("detail", {}).get("escaped_text"):
            lines.append(f"  - escaped_text: `{check['detail']['escaped_text']}`")
        elif check.get("detail", {}).get("ownership_error"):
            lines.append(f"  - ownership_error: `{check['detail']['ownership_error']}`")
    lines.extend(["", "## Telegram Availability", ""])
    telegram = data["telegram_live"]
    lines.append(f"- status: `{telegram['status']}`")
    if telegram.get("reason"):
        lines.append(f"- reason: `{telegram['reason']}`")
    if telegram.get("agent_message"):
        lines.append(f"- fallback_agent_message: {telegram['agent_message']}")
    if telegram.get("username"):
        lines.append(f"- bot_username: `{telegram['username']}`")
    lines.extend(["", "## Control Plane Result Reference", ""])
    control = data["control_plane"]
    lines.append(f"- status: `{control['status']}`")
    if control.get("reason"):
        lines.append(f"- reason: `{control['reason']}`")
    lines.append(f"- result_reference: `{data['result_reference']}`")
    lines.extend(["", "## Rollback", ""])
    for command in ROLLBACK_COMMANDS:
        lines.append(f"- `{command}`")
    lines.extend(["", "## Command Output Tails", ""])
    for result in data["verification_commands"]:
        lines.append(f"### {result['command']}")
        lines.append("")
        lines.append(f"- status: `{result['status']}`")
        if result["stdout_tail"]:
            lines.append("")
            lines.append("```text")
            lines.append(result["stdout_tail"])
            lines.append("```")
        if result["stderr_tail"]:
            lines.append("")
            lines.append("```text")
            lines.append(result["stderr_tail"])
            lines.append("```")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--task-id", default=os.environ.get("KOLIBRI_TASK_ID", DEFAULT_TASK_ID))
    parser.add_argument("--control-url", default=os.environ.get("KOLIBRI_FACTORY_CONTROL_URL", "http://10.99.0.2:9101"))
    parser.add_argument("--live-telegram", action="store_true")
    args = parser.parse_args(argv)

    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = ROOT / report_path
    report_path.parent.mkdir(parents=True, exist_ok=True)

    checks = [
        run_check("no raw JSON in readable formatter", check_no_raw_json),
        run_check("HTML escaping at Telegram payload boundary", check_html_escaping),
        run_check("duplicate getUpdates 409 ownership", check_getupdates_409_ownership),
        run_check("rollback contract present", check_rollback_contract),
    ]
    verification_results = run_verification_commands()
    telegram_live = live_telegram_probe(args.live_telegram)
    status = "PASS"
    if any(item["status"] != "PASS" for item in checks + verification_results):
        status = "FAIL"

    data = {
        "generated_at": utc_now(),
        "status": status,
        "task_id": args.task_id,
        "result_reference": str(report_path),
        "gate_command": command_line(args),
        "checks": checks,
        "verification_commands": verification_results,
        "telegram_live": telegram_live,
        "control_plane": {"status": "PENDING"},
    }
    report_path.write_text(markdown_report(data), encoding="utf-8")

    deliverable_results = run_deliverable_commands()
    verification_results = deliverable_results + verification_results
    if any(item["status"] != "PASS" for item in checks + verification_results):
        status = "FAIL"
    data["status"] = status
    data["verification_commands"] = verification_results
    report_path.write_text(markdown_report(data), encoding="utf-8")

    control = annotate_control_plane(args.control_url, args.task_id, report_path, status, verification_results)
    data["control_plane"] = control
    report_path.write_text(markdown_report(data), encoding="utf-8")

    print(json.dumps({"status": status, "report": str(report_path), "control_plane": control["status"]}, ensure_ascii=False))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
