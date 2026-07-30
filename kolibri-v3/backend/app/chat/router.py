from __future__ import annotations

import asyncio
import json
import re
import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response, StreamingResponse

from ..config import Settings
from ..database import connect_database, get_database
from ..identity import require_user
from ..schemas import UserSession
from ..security import require_mutation_auth
from .errors import ChatError
from .cancellation import cancel_run
from .events import SSE_HEADERS, encode_heartbeat, encode_sse
from .execution_adapter import (
    dispatch_chat_execution,
    prepare_chat_execution,
)
from .models import AgUiRunInput, MessageFeedbackInput, ThreadActionInput
from .service import (
    accept_run,
    apply_thread_action,
    resolve_thread,
    submit_message_feedback,
)


router = APIRouter(prefix="/v1/chat", tags=["chat"])
DatabaseDependency = Annotated[sqlite3.Connection, Depends(get_database)]
IdentityDependency = Annotated[UserSession, Depends(require_user)]
MutationAuthDependency = Annotated[None, Depends(require_mutation_auth)]
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._~-]{7,127}$")


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def _message_content(
    row: sqlite3.Row,
    attachment_rows: list[sqlite3.Row] | None = None,
) -> list[dict[str, object]]:
    raw = row["content_json"]
    if row["role"] == "assistant" and isinstance(raw, str):
        try:
            part = json.loads(raw)
        except (TypeError, ValueError):
            part = None
        if (
            isinstance(part, dict)
            and part.get("type") == "tool-call"
            and isinstance(part.get("args"), dict)
            and isinstance(part.get("result"), dict)
        ):
            return [part]
    content: list[dict[str, object]] = [
        {"type": "text", "text": str(row["content_text"])}
    ]
    for attachment in attachment_rows or []:
        attachment_id = str(attachment["attachment_id"])
        mime_type = str(attachment["mime_type"])
        content.append(
            {
                "type": (
                    "image" if mime_type.startswith("image/") else "document"
                ),
                "source": {
                    "type": "url",
                    "value": (
                        "/api/product/v1/attachments/"
                        f"{attachment_id}/content"
                    ),
                    "mimeType": mime_type,
                },
                "metadata": {
                    "filename": str(attachment["filename"]),
                },
            }
        )
    return content


@router.get("/threads")
def list_threads(
    database: DatabaseDependency,
    identity: IdentityDependency,
) -> dict[str, object]:
    rows = database.execute(
        """
        SELECT
            COALESCE(mapping.client_thread_id, thread.id) AS public_id,
            thread.project_id,
            thread.title,
            CASE
                WHEN preference.archived_at IS NOT NULL THEN 'archived'
                ELSE thread.status
            END AS effective_status,
            CASE WHEN preference.pinned_at IS NOT NULL THEN 1 ELSE 0 END
                AS is_pinned,
            thread.created_at,
            thread.updated_at,
            thread.last_message_at
        FROM chat_threads AS thread
        LEFT JOIN chat_client_threads AS mapping
         ON mapping.tenant_id = thread.tenant_id
         AND mapping.thread_id = thread.id
        LEFT JOIN chat_thread_preferences AS preference
          ON preference.tenant_id = thread.tenant_id
         AND preference.thread_id = thread.id
         AND preference.user_id = ?
        WHERE thread.tenant_id = ?
          AND preference.hidden_at IS NULL
        ORDER BY
            CASE WHEN preference.pinned_at IS NOT NULL THEN 0 ELSE 1 END,
            preference.pinned_at DESC,
            COALESCE(thread.last_message_at, thread.updated_at) DESC,
            thread.id ASC
        LIMIT 500
        """,
        (identity.user_id, identity.tenant_id),
    ).fetchall()
    return {
        "threads": [
            {
                "id": row["public_id"],
                "projectId": row["project_id"],
                "title": row["title"],
                "status": row["effective_status"],
                "pinned": bool(row["is_pinned"]),
                "createdAt": row["created_at"],
                "updatedAt": row["updated_at"],
                "lastMessageAt": row["last_message_at"],
            }
            for row in rows
        ],
        "nextCursor": None,
    }


@router.patch(
    "/threads/{thread_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def update_thread(
    thread_id: str,
    action_input: ThreadActionInput,
    database: DatabaseDependency,
    identity: IdentityDependency,
    _auth: MutationAuthDependency,
) -> Response:
    if not _SAFE_ID.fullmatch(thread_id):
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "thread_not_found",
            "Thread was not found.",
        )
    if not apply_thread_action(
        database,
        identity=identity,
        public_thread_id=thread_id,
        action_input=action_input,
    ):
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "thread_not_found",
            "Thread was not found.",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/threads/{thread_id}/messages")
def list_messages(
    thread_id: str,
    database: DatabaseDependency,
    identity: IdentityDependency,
) -> dict[str, object]:
    if not _SAFE_ID.fullmatch(thread_id):
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "thread_not_found",
            "Thread was not found.",
        )
    thread = resolve_thread(
        database,
        tenant_id=identity.tenant_id,
        public_thread_id=thread_id,
    )
    if thread is None:
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "thread_not_found",
            "Thread was not found.",
        )

    rows = database.execute(
        """
        SELECT
            message.id,
            message.client_message_id,
            message.role,
            message.content_text,
            message.content_json,
            message.created_at,
            feedback.feedback_type
        FROM chat_messages AS message
        LEFT JOIN chat_message_feedback AS feedback
          ON feedback.tenant_id = message.tenant_id
         AND feedback.message_id = message.id
         AND feedback.user_id = ?
        WHERE message.tenant_id = ? AND message.thread_id = ?
        ORDER BY message.sequence ASC
        LIMIT 2000
        """,
        (identity.user_id, identity.tenant_id, thread["id"]),
    ).fetchall()
    attachment_rows: dict[str, list[sqlite3.Row]] = {}
    for attachment in database.execute(
        """
        SELECT reference.message_id, reference.attachment_id,
               reference.filename, reference.mime_type
        FROM chat_message_attachment_refs AS reference
        JOIN chat_messages AS message
          ON message.tenant_id = reference.tenant_id
         AND message.id = reference.message_id
        WHERE reference.tenant_id = ? AND message.thread_id = ?
        ORDER BY message.sequence, reference.position
        LIMIT 20000
        """,
        (identity.tenant_id, str(thread["id"])),
    ).fetchall():
        attachment_rows.setdefault(
            str(attachment["message_id"]),
            [],
        ).append(attachment)
    return {
        "threadId": thread_id,
        "messages": [
            {
                "id": row["client_message_id"] or row["id"],
                "role": row["role"],
                "content": _message_content(
                    row,
                    attachment_rows.get(str(row["id"])),
                ),
                "createdAt": row["created_at"],
                "status": {"type": "complete", "reason": "stop"},
                "submittedFeedback": row["feedback_type"],
            }
            for row in rows
        ],
        "nextCursor": None,
    }


@router.put(
    "/threads/{thread_id}/messages/{message_id}/feedback",
    status_code=status.HTTP_204_NO_CONTENT,
)
def update_message_feedback(
    thread_id: str,
    message_id: str,
    feedback_input: MessageFeedbackInput,
    database: DatabaseDependency,
    identity: IdentityDependency,
    _auth: MutationAuthDependency,
) -> Response:
    if not _SAFE_ID.fullmatch(thread_id) or not _SAFE_ID.fullmatch(message_id):
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "message_not_found",
            "Message was not found.",
        )
    if not submit_message_feedback(
        database,
        identity=identity,
        public_thread_id=thread_id,
        public_message_id=message_id,
        feedback_input=feedback_input,
    ):
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "message_not_found",
            "Message was not found.",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _stream_run(
    *,
    settings: Settings,
    tenant_id: str,
    run_id: str,
    start_after: int = 0,
) -> object:
    cursor = start_after
    while True:
        database = connect_database(settings.database_url)
        try:
            rows = database.execute(
                """
                SELECT sequence, event_type, event_json
                FROM chat_run_events
                WHERE tenant_id = ? AND run_id = ? AND sequence > ?
                ORDER BY sequence ASC
                LIMIT 100
                """,
                (tenant_id, run_id, cursor),
            ).fetchall()
            run = (
                None
                if rows
                else database.execute(
                    """
                    SELECT status, last_event_sequence
                    FROM chat_runs
                    WHERE tenant_id = ? AND id = ?
                    LIMIT 1
                    """,
                    (tenant_id, run_id),
                ).fetchone()
            )
        finally:
            database.close()
        if rows:
            for row in rows:
                value = json.loads(str(row["event_json"]))
                value["sequence"] = int(row["sequence"])
                cursor = int(row["sequence"])
                yield encode_sse(value)
                if str(row["event_type"]) in {"RUN_FINISHED", "RUN_ERROR"}:
                    return
            continue
        if (
            run is None
            or (
                str(run["status"]) != "running"
                and cursor >= int(run["last_event_sequence"])
            )
        ):
            return
        yield encode_heartbeat()
        await asyncio.sleep(settings.product_run_poll_seconds)


def _resume_cursor(request: Request) -> int:
    raw_cursor = request.headers.get("last-event-id")
    if raw_cursor is None:
        return 0
    if (
        not raw_cursor
        or len(raw_cursor) > 20
        or not raw_cursor.isascii()
        or not raw_cursor.isdecimal()
    ):
        raise _error(
            status.HTTP_400_BAD_REQUEST,
            "run_cursor_invalid",
            "Run cursor is invalid.",
        )
    cursor = int(raw_cursor)
    if cursor > 9_223_372_036_854_775_807:
        raise _error(
            status.HTTP_400_BAD_REQUEST,
            "run_cursor_invalid",
            "Run cursor is invalid.",
        )
    return cursor


@router.get("/runs/{run_id}/events")
def resume_run(
    run_id: str,
    request: Request,
    database: DatabaseDependency,
    identity: IdentityDependency,
) -> StreamingResponse:
    """Replay one owned durable AG-UI stream after ``Last-Event-ID``."""

    if not _SAFE_ID.fullmatch(run_id):
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "run_not_found",
            "Run was not found.",
        )
    cursor = _resume_cursor(request)
    run = database.execute(
        """
        SELECT run.last_event_sequence
        FROM chat_runs AS run
        WHERE run.tenant_id = ?
          AND run.id = ?
          AND run.requested_by_user_id = ?
        LIMIT 1
        """,
        (identity.tenant_id, run_id, identity.user_id),
    ).fetchone()
    if run is None:
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "run_not_found",
            "Run was not found.",
        )
    if cursor > int(run["last_event_sequence"]):
        raise _error(
            status.HTTP_409_CONFLICT,
            "run_cursor_ahead",
            "Run cursor is ahead of the durable event stream.",
        )
    settings: Settings = request.app.state.settings
    return StreamingResponse(
        _stream_run(
            settings=settings,
            tenant_id=identity.tenant_id,
            run_id=run_id,
            start_after=cursor,
        ),
        status_code=status.HTTP_200_OK,
        media_type="text/event-stream",
        headers={
            **SSE_HEADERS,
            "X-Kolibri-Run-Id": run_id,
        },
    )


@router.post(
    "/runs/{run_id}/cancel",
    status_code=status.HTTP_204_NO_CONTENT,
)
def stop_run(
    run_id: str,
    request: Request,
    database: DatabaseDependency,
    identity: IdentityDependency,
    _auth: MutationAuthDependency,
) -> Response:
    if not _SAFE_ID.fullmatch(run_id):
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "run_not_found",
            "Run was not found.",
        )
    result = cancel_run(
        database,
        tenant_id=identity.tenant_id,
        user_id=identity.user_id,
        run_id=run_id,
    )
    if result is None:
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "run_not_found",
            "Run was not found.",
        )
    request.app.state.run_cancellations.cancel(
        identity.tenant_id,
        result.run_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/ag-ui")
def start_ag_ui_run(
    run_input: AgUiRunInput,
    request: Request,
    database: DatabaseDependency,
    identity: IdentityDependency,
    _auth: MutationAuthDependency,
) -> StreamingResponse:
    """Commit the run before opening a resumable AG-UI event projection."""

    settings: Settings = request.app.state.settings
    try:
        prepared = prepare_chat_execution(
            request,
            database,
            settings=settings,
            identity=identity,
            run_input=run_input,
        )
        accepted = accept_run(
            database,
            settings=settings,
            identity=identity,
            run_input=run_input,
            prepared=prepared,
        )
    except ChatError as exc:
        raise _error(exc.status_code, exc.code, exc.message) from exc
    dispatch_chat_execution(
        request,
        settings=settings,
        accepted=accepted,
    )
    return StreamingResponse(
        _stream_run(
            settings=settings,
            tenant_id=accepted.tenant_id,
            run_id=accepted.run_id,
        ),
        status_code=status.HTTP_200_OK,
        media_type="text/event-stream",
        headers={
            **SSE_HEADERS,
            "X-Kolibri-Run-Id": accepted.run_id,
        },
    )
