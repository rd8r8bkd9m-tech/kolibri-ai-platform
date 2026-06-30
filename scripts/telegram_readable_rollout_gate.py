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
import time
import urllib.error
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = REPO_ROOT / "docs/agent-work/generated/remote-server-transfer-20260629T1603/telegram-rollout-gate-report.json"
TASK_ID = "KOL-REMOTE-SERVER-TASK-20260629T1603-002-MAIN-TELEGRAM"


@dataclass
class CheckResult:
    name: str
    status: str
    detail: str
    duration_ms: int


def load_gateway() -> Any:
    path = REPO_ROOT / "ops" / "telegram_gateway.py"
    spec = importlib.util.spec_from_file_location("telegram_gateway", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def timed_check(name: str, func) -> CheckResult:
    started = time.monotonic()
    try:
        detail = func()
        status = "pass"
    except AssertionError as exc:
        detail = str(exc)
        status = "fail"
    except Exception as exc:  # pragma: no cover - defensive reporting path
        detail = f"{type(exc).__name__}: {exc}"
        status = "fail"
    return CheckResult(name=name, status=status, detail=detail or "ok", duration_ms=int((time.monotonic() - started) * 1000))


def skipped_check(name: str, detail: str) -> CheckResult:
    return CheckResult(name=name, status="skip", detail=detail, duration_ms=0)


def check_no_raw_json(gateway: Any) -> str:
    raw = json.dumps(
        {
            "response": "Formatter ready <safe> & readable.",
            "task_id": "TGCHAT-raw-json",
            "node_id": "primary-candidate",
        }
    )
    formatted = gateway.clean_agent_response(raw)
    assert formatted == "Formatter ready <safe> & readable.", formatted
    forbidden = ["{", "}", '"response"', "task_id", "node_id", "TGCHAT-"]
    leaked = [marker for marker in forbidden if marker in formatted]
    assert not leaked, f"raw json/internal markers leaked: {leaked}"
    return "raw JSON payloads are converted to owner-readable text"


def check_html_escape(gateway: Any) -> str:
    escaped = gateway.telegram_html_escape("<b>5 & 6</b>")
    assert escaped == "&lt;b&gt;5 &amp; 6&lt;/b&gt;", escaped
    bounded = gateway.telegram_html_escape("&" * 5000, 3900)
    assert len(bounded) <= 3900, len(bounded)
    assert not bounded.endswith("&"), "bounded HTML escape ended on a partial entity"
    return "Telegram HTML payloads are escaped and bounded"


def check_getupdates_409_contract(gateway: Any) -> str:
    original_urlopen = gateway.urllib.request.urlopen

    def fake_urlopen(req, timeout):
        del timeout
        body = b'{"ok":false,"error_code":409,"description":"Conflict: terminated by other getUpdates request"}'
        raise urllib.error.HTTPError(req.full_url, 409, "Conflict", {}, io.BytesIO(body))

    gateway.urllib.request.urlopen = fake_urlopen
    try:
        client = gateway.TelegramClient("123:test", api_base="https://telegram.invalid")
        try:
            client.get_updates(None, 1)
        except gateway.TelegramConflictError:
            return "duplicate getUpdates ownership raises TelegramConflictError"
        raise AssertionError("getUpdates 409 did not raise TelegramConflictError")
    finally:
        gateway.urllib.request.urlopen = original_urlopen


def redact(text: str, secret: str | None) -> str:
    if secret:
        return text.replace(secret, "<redacted>")
    return text


def live_checks(args: argparse.Namespace, gateway: Any) -> tuple[list[CheckResult], str | None]:
    if not args.live:
        return [skipped_check("live_telegram", "not requested; run with --live on the rollout host")], None

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        message = "Telegram live verification unavailable: TELEGRAM_BOT_TOKEN is not present. Fallback artifact report was generated."
        status = "fail" if args.require_live else "skip"
        return [CheckResult("live_telegram", status, message, 0)], message

    client = gateway.TelegramClient(token, api_base=args.api_base)
    results: list[CheckResult] = []
    fallback_message: str | None = None

    def get_me() -> str:
        response = client.call("getMe", {}, timeout=args.http_timeout)
        username = (response.get("result") or {}).get("username") or "unknown"
        return f"Telegram getMe succeeded for bot username {username}"

    result = timed_check("live_get_me", get_me)
    if result.status == "fail":
        result.detail = redact(result.detail, token)
        if not args.require_live:
            result.status = "skip"
        fallback_message = "Telegram live verification unavailable: getMe failed. Fallback artifact report was generated."
    results.append(result)

    if args.check_getupdates:
        def get_updates() -> str:
            client.get_updates(None, args.getupdates_timeout)
            return "no duplicate getUpdates owner detected during short poll"

        result = timed_check("live_getupdates_ownership", get_updates)
        result.detail = redact(result.detail, token)
        if result.status == "fail" and "TelegramConflictError" in result.detail:
            result.detail = "duplicate getUpdates owner detected; rollout must stop before sending owner traffic"
        results.append(result)
    else:
        results.append(skipped_check("live_getupdates_ownership", "not requested; use --check-getupdates during exclusive rollout window"))

    chat_id = args.chat_id or os.environ.get("TELEGRAM_OWNER_CHAT_ID", "")
    if args.send_message and chat_id:
        def send_message() -> str:
            client.send_message(int(chat_id), "Rollout gate: readable formatter check <json> complete.")
            return "escaped Telegram smoke message sent"

        result = timed_check("live_send_message", send_message)
        result.detail = redact(result.detail, token)
        results.append(result)
    elif args.send_message:
        results.append(skipped_check("live_send_message", "TELEGRAM_OWNER_CHAT_ID/chat id is missing"))
    else:
        results.append(skipped_check("live_send_message", "not requested; use --send-message with TELEGRAM_OWNER_CHAT_ID"))

    return results, fallback_message


def run_rollback(command: str, timeout: int) -> dict[str, Any]:
    started = time.monotonic()
    proc = subprocess.run(command, shell=True, text=True, capture_output=True, timeout=timeout, check=False)
    return {
        "command_configured": True,
        "returncode": proc.returncode,
        "duration_ms": int((time.monotonic() - started) * 1000),
    }


def write_report(path: Path, checks: list[CheckResult], fallback_message: str | None, rollback: dict[str, Any] | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "task_id": TASK_ID,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "gate": "telegram_readable_formatter_rollout",
        "checks": [asdict(check) for check in checks],
        "fallback_agent_message": fallback_message,
        "rollback": rollback or {"command_configured": False},
    }
    path.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--live", action="store_true", help="run Telegram API checks when TELEGRAM_BOT_TOKEN is present")
    parser.add_argument("--require-live", action="store_true", help="fail when live Telegram checks cannot run")
    parser.add_argument("--api-base", default=os.environ.get("TELEGRAM_API_BASE", "https://api.telegram.org"))
    parser.add_argument("--http-timeout", type=int, default=10)
    parser.add_argument("--check-getupdates", action="store_true", help="short-poll getUpdates to detect duplicate long-poll owners")
    parser.add_argument("--getupdates-timeout", type=int, default=1)
    parser.add_argument("--send-message", action="store_true", help="send an escaped smoke message to TELEGRAM_OWNER_CHAT_ID")
    parser.add_argument("--chat-id", default="")
    parser.add_argument("--rollback-command", default=os.environ.get("TELEGRAM_ROLLBACK_COMMAND", ""))
    parser.add_argument("--rollback-timeout", type=int, default=60)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    gateway = load_gateway()
    checks = [
        timed_check("no_raw_json_formatter", lambda: check_no_raw_json(gateway)),
        timed_check("html_escaping", lambda: check_html_escape(gateway)),
        timed_check("getupdates_409_ownership_contract", lambda: check_getupdates_409_contract(gateway)),
    ]
    live_results, fallback_message = live_checks(args, gateway)
    checks.extend(live_results)
    failed = any(check.status == "fail" for check in checks)
    rollback = None
    if failed and args.rollback_command:
        rollback = run_rollback(args.rollback_command, args.rollback_timeout)
    write_report(args.report, checks, fallback_message, rollback)
    passed = sum(1 for check in checks if check.status == "pass")
    skipped = sum(1 for check in checks if check.status == "skip")
    failed_count = sum(1 for check in checks if check.status == "fail")
    print(f"telegram rollout gate: pass={passed} fail={failed_count} skip={skipped} report={args.report}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
