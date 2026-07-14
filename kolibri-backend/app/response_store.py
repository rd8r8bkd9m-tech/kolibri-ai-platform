"""PostgreSQL/SQLite durable authority for public Responses and SSE events."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import uuid
from typing import Any

from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.models import PublicResponseDB, PublicResponseEventDB


class ResponseIdempotencyConflict(RuntimeError):
    """The owner/idempotency tuple is already claimed by another response."""


def _detached(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


def save_response_record(record: dict[str, Any]) -> None:
    response_id = str(record["id"])
    owner_scope = str(record.get("owner_scope") or "")
    status = str(record.get("status") or "in_progress")
    if not owner_scope:
        raise ValueError("response_owner_scope_required")
    payload = _detached({key: value for key, value in record.items() if key != "events"})
    events = _detached(record.get("events") or [])
    now = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        row = db.get(PublicResponseDB, response_id)
        if row is None:
            row = PublicResponseDB(
                id=response_id,
                owner_scope=owner_scope,
                status=status,
                idempotency_key=record.get("idempotency_key"),
                request_hash=record.get("request_hash"),
                payload=payload,
                created_at=now,
                updated_at=now,
            )
            db.add(row)
        else:
            if row.owner_scope != owner_scope:
                raise ValueError("response_owner_scope_immutable")
            row.status = status
            row.idempotency_key = record.get("idempotency_key")
            row.request_hash = record.get("request_hash")
            row.payload = payload
            row.updated_at = now
        existing_sequences = {
            int(value[0])
            for value in db.query(PublicResponseEventDB.sequence)
            .filter(PublicResponseEventDB.response_id == response_id)
            .all()
        }
        for event in events:
            sequence = int(event["sequence"])
            if sequence in existing_sequences:
                continue
            db.add(PublicResponseEventDB(
                id=str(uuid.uuid4()),
                response_id=response_id,
                sequence=sequence,
                event_type=str(event["type"]),
                payload=event,
                created_at=now,
            ))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ResponseIdempotencyConflict("response_idempotency_conflict") from exc
    finally:
        db.close()


def _record(row: PublicResponseDB) -> dict[str, Any]:
    payload = _detached(row.payload or {})
    events = [_detached(event.payload) for event in row.events]
    payload.update({
        "id": row.id,
        "owner_scope": row.owner_scope,
        "status": row.status,
        "idempotency_key": row.idempotency_key,
        "request_hash": row.request_hash,
        "events": events,
        "last_sequence": max((int(event["sequence"]) for event in events), default=0),
    })
    return payload


def load_response_record(response_id: str) -> dict[str, Any] | None:
    db = SessionLocal()
    try:
        row = db.get(PublicResponseDB, response_id)
        return _record(row) if row is not None else None
    finally:
        db.close()


def find_idempotent_response(owner_scope: str, idempotency_key: str) -> dict[str, Any] | None:
    db = SessionLocal()
    try:
        row = (
            db.query(PublicResponseDB)
            .filter(
                PublicResponseDB.owner_scope == owner_scope,
                PublicResponseDB.idempotency_key == idempotency_key,
            )
            .first()
        )
        return _record(row) if row is not None else None
    finally:
        db.close()


def recover_interrupted_responses() -> list[str]:
    """Fail pre-start nonterminal responses exactly once and make retry safe.

    The current FastAPI authority cannot safely resume an arbitrary provider
    subprocess after its process has disappeared.  On application startup we
    therefore choose the conservative durable transition instead of leaving
    an eternal ``in_progress`` record or claiming completion.
    """

    db = SessionLocal()
    recovered: list[str] = []
    now = datetime.now(timezone.utc)
    try:
        rows = (
            db.query(PublicResponseDB)
            .filter(PublicResponseDB.status.notin_(("completed", "failed", "cancelled")))
            .all()
        )
        for row in rows:
            events = sorted(row.events, key=lambda event: int(event.sequence))
            sequence = max((int(event.sequence) for event in events), default=0) + 1
            error = {
                "code": "response_interrupted",
                "recoverable": True,
                "capability": None,
            }
            payload = _detached(row.payload or {})
            payload.update({
                "status": "failed",
                "content": str(payload.get("content") or ""),
                "error": error,
                "interrupted_at": now.isoformat(),
                "last_sequence": sequence,
            })
            event_payload = {
                "type": "response.failed",
                "response_id": row.id,
                "sequence": sequence,
                "status": "failed",
                "error": error,
            }
            row.status = "failed"
            row.payload = payload
            row.updated_at = now
            db.add(PublicResponseEventDB(
                id=str(uuid.uuid4()),
                response_id=row.id,
                sequence=sequence,
                event_type="response.failed",
                payload=event_payload,
                created_at=now,
            ))
            recovered.append(str(row.id))
        db.commit()
        return recovered
    except IntegrityError:
        # Another startup authority may have completed the same transition.
        db.rollback()
        return []
    finally:
        db.close()
