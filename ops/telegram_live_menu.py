#!/usr/bin/env python3
"""Safely repair or restore the live Telegram bot command menu.

This script intentionally never prints the bot token or request URL. It reads
the token from TELEGRAM_BOT_TOKEN by default and writes rollback state as JSON.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


MINIMAL_OWNER_COMMANDS = [
    {"command": "start", "description": "Открыть Kolibri"},
    {"command": "status", "description": "Проверить состояние фабрики"},
    {"command": "help", "description": "Как работать с ботом"},
]
DEFAULT_MENU_BUTTON = {"type": "default"}


class BotApiError(RuntimeError):
    pass


def load_env_file(path: Path) -> None:
    if not path.exists():
        raise SystemExit(f"env file not found: {path}")
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


def token_from_env() -> str:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN is required")
    return token


def owner_ids_from_env() -> list[int]:
    owner_ids: list[int] = []
    for item in os.environ.get("TELEGRAM_OWNER_IDS", "").replace(";", ",").split(","):
        item = item.strip()
        if item:
            owner_ids.append(int(item))
    return owner_ids


def bot_api_call(token: str, method: str, payload: dict[str, Any] | None = None, timeout: int = 30) -> dict[str, Any]:
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = urllib.parse.urlencode(payload or {}).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise BotApiError(f"Bot API {method} failed: HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise BotApiError(f"Bot API {method} failed: {exc.reason}") from exc
    try:
        response = json.loads(body)
    except json.JSONDecodeError as exc:
        raise BotApiError(f"Bot API {method} returned invalid JSON") from exc
    if not response.get("ok"):
        description = response.get("description") or "unknown error"
        raise BotApiError(f"Bot API {method} failed: {description}")
    return response


def get_commands(token: str, scope: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    payload = {"scope": json.dumps(scope, ensure_ascii=False, separators=(",", ":"))} if scope else None
    return list(bot_api_call(token, "getMyCommands", payload).get("result") or [])


def get_menu_button(token: str, chat_id: int | None = None) -> dict[str, Any] | None:
    payload = {"chat_id": chat_id} if chat_id is not None else None
    return bot_api_call(token, "getChatMenuButton", payload).get("result")


def set_commands(token: str, commands: list[dict[str, str]], scope: dict[str, Any] | None = None) -> None:
    payload: dict[str, Any] = {"commands": json.dumps(commands, ensure_ascii=False, separators=(",", ":"))}
    if scope:
        payload["scope"] = json.dumps(scope, ensure_ascii=False, separators=(",", ":"))
    bot_api_call(token, "setMyCommands", payload)


def set_menu_button(token: str, menu_button: dict[str, Any] | None, chat_id: int | None = None) -> None:
    payload: dict[str, Any] = {}
    if chat_id is not None:
        payload["chat_id"] = chat_id
    if menu_button:
        payload["menu_button"] = json.dumps(menu_button, ensure_ascii=False, separators=(",", ":"))
    bot_api_call(token, "setChatMenuButton", payload)


def owner_scope(chat_id: int) -> dict[str, Any]:
    return {"type": "chat", "chat_id": chat_id}


def backup_state(token: str, path: Path, owner_ids: list[int] | None = None) -> dict[str, Any]:
    owner_ids = owner_ids or []
    state = {
        "created_at": int(time.time()),
        "commands": get_commands(token),
        "private_chat_commands": get_commands(token, {"type": "all_private_chats"}),
        "owner_chat_commands": [get_commands(token, owner_scope(owner_id)) for owner_id in owner_ids],
        "menu_button": get_menu_button(token),
        "owner_chat_menu_buttons": [get_menu_button(token, owner_id) for owner_id in owner_ids],
        "owner_count": len(owner_ids),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return state


def read_backup(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"rollback backup not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def verify_minimal(
    commands: list[dict[str, Any]],
    private_commands: list[dict[str, Any]],
    owner_commands: list[list[dict[str, Any]]],
    owner_menu_buttons: list[dict[str, Any] | None],
) -> bool:
    if commands != MINIMAL_OWNER_COMMANDS or private_commands != MINIMAL_OWNER_COMMANDS:
        return False
    if any(scoped != MINIMAL_OWNER_COMMANDS for scoped in owner_commands):
        return False
    return all((button or {}).get("type") in {"default", "commands"} for button in owner_menu_buttons)


def command_names(commands: list[dict[str, Any]]) -> list[str]:
    return [str(command.get("command", "")) for command in commands]


def apply_minimal(token: str, backup_path: Path, owner_ids: list[int], skip_backup: bool = False) -> dict[str, Any]:
    if not skip_backup:
        backup_state(token, backup_path, owner_ids)
    set_commands(token, MINIMAL_OWNER_COMMANDS)
    set_commands(token, MINIMAL_OWNER_COMMANDS, {"type": "all_private_chats"})
    for owner_id in owner_ids:
        set_commands(token, MINIMAL_OWNER_COMMANDS, owner_scope(owner_id))
        set_menu_button(token, DEFAULT_MENU_BUTTON, owner_id)
    set_menu_button(token, DEFAULT_MENU_BUTTON)
    commands = get_commands(token)
    private_commands = get_commands(token, {"type": "all_private_chats"})
    owner_commands = [get_commands(token, owner_scope(owner_id)) for owner_id in owner_ids]
    menu_button = get_menu_button(token)
    owner_menu_buttons = [get_menu_button(token, owner_id) for owner_id in owner_ids]
    ok = verify_minimal(commands, private_commands, owner_commands, owner_menu_buttons)
    return {
        "ok": ok,
        "commands": command_names(commands),
        "private_commands": command_names(private_commands),
        "owner_command_sets": [command_names(scoped) for scoped in owner_commands],
        "menu_button_type": (menu_button or {}).get("type"),
        "owner_menu_button_types": [(button or {}).get("type") for button in owner_menu_buttons],
        "owner_count": len(owner_ids),
    }


def rollback(token: str, backup_path: Path, owner_ids: list[int]) -> dict[str, Any]:
    state = read_backup(backup_path)
    commands = list(state.get("commands") or [])
    private_commands = list(state.get("private_chat_commands") or commands)
    owner_command_sets = list(state.get("owner_chat_commands") or [private_commands for _ in owner_ids])
    menu_button = state.get("menu_button")
    owner_menu_buttons = list(state.get("owner_chat_menu_buttons") or [menu_button for _ in owner_ids])
    set_commands(token, commands)
    set_commands(token, private_commands, {"type": "all_private_chats"})
    for idx, owner_id in enumerate(owner_ids):
        owner_commands = owner_command_sets[idx] if idx < len(owner_command_sets) else private_commands
        owner_menu_button = owner_menu_buttons[idx] if idx < len(owner_menu_buttons) else menu_button
        set_commands(token, owner_commands, owner_scope(owner_id))
        set_menu_button(token, owner_menu_button if isinstance(owner_menu_button, dict) else None, owner_id)
    set_menu_button(token, menu_button if isinstance(menu_button, dict) else None)
    restored_commands = get_commands(token)
    restored_private_commands = get_commands(token, {"type": "all_private_chats"})
    restored_owner_commands = [get_commands(token, owner_scope(owner_id)) for owner_id in owner_ids]
    restored_menu = get_menu_button(token)
    restored_owner_menus = [get_menu_button(token, owner_id) for owner_id in owner_ids]
    return {
        "ok": restored_commands == commands
        and restored_private_commands == private_commands
        and restored_owner_commands == owner_command_sets[: len(owner_ids)]
        and restored_menu == menu_button
        and restored_owner_menus == owner_menu_buttons[: len(owner_ids)],
        "commands": command_names(restored_commands),
        "private_commands": command_names(restored_private_commands),
        "owner_command_sets": [command_names(scoped) for scoped in restored_owner_commands],
        "menu_button_type": (restored_menu or {}).get("type"),
        "owner_menu_button_types": [(button or {}).get("type") for button in restored_owner_menus],
        "owner_count": len(owner_ids),
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Repair or restore the live Telegram command menu.")
    parser.add_argument(
        "--backup-path",
        default="artifacts/runtime/telegram-live-menu-rollback.json",
        help="Path for rollback JSON with prior commands/menu button.",
    )
    parser.add_argument("--env-file", help="Optional env file to load TELEGRAM_BOT_TOKEN from.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("backup")
    apply_parser = subparsers.add_parser("apply-minimal")
    apply_parser.add_argument("--skip-backup", action="store_true", help="Do not overwrite an existing rollback backup.")
    subparsers.add_parser("verify")
    subparsers.add_parser("rollback")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.env_file:
        load_env_file(Path(args.env_file))
    token = token_from_env()
    owner_ids = owner_ids_from_env()
    backup_path = Path(args.backup_path)
    if args.command == "backup":
        state = backup_state(token, backup_path, owner_ids)
        result = {
            "ok": True,
            "backup_path": str(backup_path),
            "commands": command_names(state["commands"]),
            "private_commands": command_names(state["private_chat_commands"]),
            "menu_button_type": (state.get("menu_button") or {}).get("type"),
            "owner_count": len(owner_ids),
        }
    elif args.command == "apply-minimal":
        result = apply_minimal(token, backup_path, owner_ids, skip_backup=args.skip_backup)
        result["backup_path"] = str(backup_path)
    elif args.command == "verify":
        commands = get_commands(token)
        private_commands = get_commands(token, {"type": "all_private_chats"})
        owner_commands = [get_commands(token, owner_scope(owner_id)) for owner_id in owner_ids]
        menu_button = get_menu_button(token)
        owner_menu_buttons = [get_menu_button(token, owner_id) for owner_id in owner_ids]
        result = {
            "ok": verify_minimal(commands, private_commands, owner_commands, owner_menu_buttons),
            "commands": command_names(commands),
            "private_commands": command_names(private_commands),
            "owner_command_sets": [command_names(scoped) for scoped in owner_commands],
            "menu_button_type": (menu_button or {}).get("type"),
            "owner_menu_button_types": [(button or {}).get("type") for button in owner_menu_buttons],
            "owner_count": len(owner_ids),
        }
    elif args.command == "rollback":
        result = rollback(token, backup_path, owner_ids)
    else:  # pragma: no cover - argparse prevents this.
        raise SystemExit(f"unsupported command: {args.command}")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
