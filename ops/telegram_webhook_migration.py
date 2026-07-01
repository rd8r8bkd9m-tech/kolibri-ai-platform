#!/usr/bin/env python3
"""Owner-approved Telegram webhook migration helpers.

This module is intentionally separate from kolibri-telegram-gateway startup.
It must not be imported or called by the systemd long-polling receiver path.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from telegram_gateway import TelegramClient


DELETE_WEBHOOK_APPROVAL = "DELETE_WEBHOOK_FOR_LONG_POLLING_MIGRATION"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Owner-approved Telegram delivery migration")
    subparsers = parser.add_subparsers(dest="command", required=True)
    delete = subparsers.add_parser("delete-webhook", help="delete Telegram webhook before a long-polling migration")
    delete.add_argument(
        "--owner-approved",
        required=True,
        help=f"must equal {DELETE_WEBHOOK_APPROVAL}",
    )
    delete.add_argument(
        "--drop-pending-updates",
        action="store_true",
        help="also ask Telegram to drop queued updates during the migration",
    )
    delete.add_argument("--api-base", default=os.environ.get("TELEGRAM_API_BASE", "https://api.telegram.org"))
    return parser


def delete_webhook_for_owner_approved_migration(
    token: str,
    owner_approved: str,
    *,
    drop_pending_updates: bool = False,
    api_base: str = "https://api.telegram.org",
) -> dict[str, Any]:
    if owner_approved != DELETE_WEBHOOK_APPROVAL:
        raise SystemExit("owner approval is required for Telegram webhook deletion")
    client = TelegramClient(token, api_base=api_base, allow_delivery_state_mutation=True)
    payload = {"drop_pending_updates": "true" if drop_pending_updates else "false"}
    return client.call("deleteWebhook", payload)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN is required")
    if args.command == "delete-webhook":
        delete_webhook_for_owner_approved_migration(
            token,
            args.owner_approved,
            drop_pending_updates=args.drop_pending_updates,
            api_base=args.api_base,
        )
        print("telegram webhook migration completed")
        return 0
    raise SystemExit(f"unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
