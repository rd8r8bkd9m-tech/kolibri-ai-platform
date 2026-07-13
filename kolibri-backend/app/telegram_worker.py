"""Canonical durable Telegram outbound worker.

The HTTP receiver never runs providers.  This process claims persisted update
rows, sends a visible acknowledgement, invokes the same Responses service as
the Web Shell, and edits/delivers the terminal result exactly once per normal
state transition.  No token or raw upstream error is logged.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import uuid

from app.database import SessionLocal, engine
from app.routers.telegram import (
    TelegramWorkerError,
    claim_next_update,
    mark_update_failure,
    process_claimed_update,
    verify_bot_identity,
)
from app.schema_migrations import ensure_database_schema
from app.project_handoff import validate_project_handoff_configuration


def _worker_id() -> str:
    configured = os.getenv("KOLIBRI_TELEGRAM_WORKER_ID", "").strip()
    if configured:
        return configured[:120]
    return f"telegram:{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


def _poll_interval() -> float:
    raw = os.getenv("KOLIBRI_TELEGRAM_POLL_SECONDS", "1").strip()
    try:
        value = float(raw)
    except ValueError:
        value = 1.0
    return min(max(value, 0.1), 30.0)


def _emit(event: str, **fields) -> None:
    safe = {"event": event, **fields}
    print(json.dumps(safe, ensure_ascii=False, sort_keys=True), flush=True)


async def _identity_probe() -> dict:
    with SessionLocal() as db:
        return await verify_bot_identity(db)


async def _run_one(worker_id: str) -> bool:
    with SessionLocal() as db:
        row_id = claim_next_update(db, worker_id)
    if not row_id:
        return False
    try:
        with SessionLocal() as db:
            result = await process_claimed_update(db, row_id, worker_id)
        _emit(
            "telegram.update.completed",
            update_id=result["update_id"],
            project_id=result["project_id"],
            response_id=result["response_id"],
            delivery_method=result["delivery_method"],
        )
    except TelegramWorkerError as exc:
        with SessionLocal() as db:
            mark_update_failure(db, row_id, worker_id, exc.code)
        _emit("telegram.update.retry", row_id=row_id, error_code=exc.code)
    except Exception:
        with SessionLocal() as db:
            mark_update_failure(db, row_id, worker_id, "telegram_worker_unclassified_failure")
        _emit(
            "telegram.update.retry",
            row_id=row_id,
            error_code="telegram_worker_unclassified_failure",
        )
    return True


async def _main(*, once: bool, check_identity: bool) -> int:
    if os.getenv("KOLIBRI_PUBLIC_BASE_URL", "").strip():
        validate_project_handoff_configuration()
    ensure_database_schema(engine)
    try:
        identity = await _identity_probe()
    except TelegramWorkerError as exc:
        _emit("telegram.identity.failed", error_code=exc.code)
        return 2
    _emit(
        "telegram.identity.verified",
        username=identity["username"],
        verified=identity["verified"],
    )
    if check_identity:
        return 0

    worker_id = _worker_id()
    while True:
        processed = await _run_one(worker_id)
        if once:
            return 0
        if not processed:
            await asyncio.sleep(_poll_interval())


def main() -> int:
    parser = argparse.ArgumentParser(description="Kolibri canonical Telegram worker")
    parser.add_argument("--once", action="store_true", help="process at most one queued update")
    parser.add_argument(
        "--check-identity",
        action="store_true",
        help="run a sanitised getMe check without processing updates",
    )
    args = parser.parse_args()
    return asyncio.run(_main(once=args.once, check_identity=args.check_identity))


if __name__ == "__main__":
    raise SystemExit(main())
