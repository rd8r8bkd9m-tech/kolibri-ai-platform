#!/usr/bin/env python3
"""Safe Telegram Mini App smoke checks for Kolibri."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


CANONICAL_MINIAPP_URL = "https://kolibriai.ru"


def configured_miniapp_url(env: dict[str, str] | None = None) -> str:
    env = env or os.environ
    return (
        env.get("TELEGRAM_MINIAPP_URL")
        or env.get("KOLIBRI_MINIAPP_URL")
        or env.get("TELEGRAM_MINIAPP_DEFAULT_URL")
        or CANONICAL_MINIAPP_URL
    ).strip()


def check(name: str, ok: bool, detail: str, **extra: Any) -> dict[str, Any]:
    result = {"name": name, "ok": ok, "detail": detail}
    result.update(extra)
    return result


def validate_miniapp_url(url: str) -> list[dict[str, Any]]:
    parsed = urllib.parse.urlparse(url)
    checks = [
        check("miniapp_url_present", bool(url), "Mini App URL is configured" if url else "Mini App URL is empty"),
        check(
            "miniapp_url_https",
            parsed.scheme == "https",
            "Telegram Web Apps require HTTPS URLs",
            scheme=parsed.scheme or None,
        ),
        check("miniapp_url_host", bool(parsed.netloc), "Mini App URL has a host", host=parsed.netloc or None),
    ]
    return checks


def fetch_miniapp(url: str, timeout: float) -> list[dict[str, Any]]:
    req = urllib.request.Request(url, headers={"User-Agent": "KolibriMiniappSmoke/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(512_000).decode("utf-8", "replace")
            final_url = resp.geturl()
            status = getattr(resp, "status", 200)
            content_type = resp.headers.get("content-type")
    except urllib.error.HTTPError as exc:
        return [check("miniapp_http", False, f"HTTP {exc.code}", status=exc.code)]
    except Exception as exc:
        return [check("miniapp_http", False, f"{type(exc).__name__}: {exc}", error_type=type(exc).__name__)]

    return [
        check("miniapp_http", 200 <= status < 400, "Mini App page responded", status=status, final_url=final_url, content_type=content_type),
        check(
            "miniapp_telegram_sdk",
            "telegram.org/js/telegram-web-app.js" in body,
            "HTML includes Telegram WebApp SDK",
        ),
        check(
            "miniapp_frontend_shell",
            'id="root"' in body or "/assets/" in body,
            "HTML looks like the Kolibri frontend shell",
        ),
    ]


def telegram_call(api_base: str, token: str, method: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    data = urllib.parse.urlencode(payload).encode("utf-8")
    url = f"{api_base.rstrip('/')}/bot{token}/{method}"
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def check_telegram_bot(api_base: str, token: str, timeout: float) -> list[dict[str, Any]]:
    if not token:
        return [check("telegram_token_present", False, "TELEGRAM_BOT_TOKEN is not set")]
    try:
        response = telegram_call(api_base, token, "getMe", {}, timeout)
    except Exception as exc:
        return [check("telegram_get_me", False, f"{type(exc).__name__}: {exc}", error_type=type(exc).__name__)]
    user = response.get("result") or {}
    return [
        check("telegram_get_me", bool(response.get("ok")), "Telegram bot API answered", username=user.get("username")),
    ]


def apply_menu_button(api_base: str, token: str, url: str, text: str, timeout: float) -> list[dict[str, Any]]:
    if not token:
        return [check("telegram_menu_button", False, "TELEGRAM_BOT_TOKEN is required to apply menu button")]
    payload = {
        "menu_button": json.dumps(
            {"type": "web_app", "text": text[:64], "web_app": {"url": url}},
            ensure_ascii=False,
            separators=(",", ":"),
        )
    }
    try:
        response = telegram_call(api_base, token, "setChatMenuButton", payload, timeout)
    except Exception as exc:
        return [check("telegram_menu_button", False, f"{type(exc).__name__}: {exc}", error_type=type(exc).__name__)]
    return [check("telegram_menu_button", bool(response.get("ok")), "Telegram chat menu button updated")]


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    url = args.miniapp_url or configured_miniapp_url()
    checks: list[dict[str, Any]] = validate_miniapp_url(url)
    if not args.skip_network and all(item["ok"] for item in checks):
        checks.extend(fetch_miniapp(url, args.timeout))
    if args.check_bot:
        checks.extend(check_telegram_bot(args.api_base, os.environ.get("TELEGRAM_BOT_TOKEN", ""), args.timeout))
    if args.apply_menu:
        checks.extend(apply_menu_button(args.api_base, os.environ.get("TELEGRAM_BOT_TOKEN", ""), url, args.menu_text, args.timeout))
    return {"ok": all(item["ok"] for item in checks), "miniapp_url": url, "checks": checks}


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Kolibri Telegram Mini App wiring without printing secrets.")
    parser.add_argument("--miniapp-url", default="", help="Override Mini App URL for this check.")
    parser.add_argument("--api-base", default=os.environ.get("TELEGRAM_API_BASE", "https://api.telegram.org"))
    parser.add_argument("--timeout", type=float, default=float(os.environ.get("TELEGRAM_MINIAPP_SMOKE_TIMEOUT", "8")))
    parser.add_argument("--skip-network", action="store_true", help="Only validate local URL configuration.")
    parser.add_argument("--check-bot", action="store_true", help="Call Telegram getMe if TELEGRAM_BOT_TOKEN is set.")
    parser.add_argument("--apply-menu", action="store_true", help="Apply setChatMenuButton. This changes bot configuration.")
    parser.add_argument("--menu-text", default=os.environ.get("TELEGRAM_MINIAPP_BUTTON_TEXT", "Открыть Kolibri"))
    args = parser.parse_args()

    report = build_report(args)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
