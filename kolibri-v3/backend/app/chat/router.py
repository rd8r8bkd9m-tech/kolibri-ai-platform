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
from ..direct_model_runtime import execute_direct_run
from ..identity import require_user
from ..schemas import UserSession
from ..security import require_csrf
from .errors import ChatError
from .events import SSE_HEADERS, encode_heartbeat, encode_sse
from .models import AgUiRunInput, MessageFeedbackInput, ThreadActionInput
from .service import (
    AcceptedRun,
    accept_run,
    apply_thread_action,
    resolve_thread,
    submit_message_feedback,
)


router = APIRouter(prefix="/v1/chat", tags=["chat"])
DatabaseDependency = Annotated[sqlite3.Connection, Depends(get_database)]
IdentityDependency = Annotated[UserSession, Depends(require_user)]
CsrfDependency = Annotated[None, Depends(require_csrf)]
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._~-]{7,127}$")


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def _message_content(row: sqlite3.Row) -> list[dict[str, object]]:
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
    return [{"type": "text", "text": str(row["content_text"])}]


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
    _csrf: CsrfDependency,
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
    return {
        "threadId": thread_id,
        "messages": [
            {
                "id": row["client_message_id"] or row["id"],
                "role": row["role"],
                "content": _message_content(row),
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
    _csrf: CsrfDependency,
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
    accepted: AcceptedRun,
) -> object:
    cursor = 0
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
                (accepted.tenant_id, accepted.run_id, cursor),
            ).fetchall()
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
        yield encode_heartbeat()
        await asyncio.sleep(settings.product_run_poll_seconds)


@router.post("/ag-ui")
def start_ag_ui_run(
    run_input: AgUiRunInput,
    request: Request,
    database: DatabaseDependency,
    identity: IdentityDependency,
    _csrf: CsrfDependency,
) -> StreamingResponse:
    """Commit the run before opening a resumable AG-UI event projection."""

    settings: Settings = request.app.state.settings
    try:
        accepted = accept_run(
            database,
            settings=settings,
            identity=identity,
            run_input=run_input,
        )
    except ChatError as exc:
        raise _error(exc.status_code, exc.code, exc.message) from exc
    if settings.direct_model_runtime_enabled and not accepted.replayed:
        executor = request.app.state.direct_model_executor
        if executor is None:
            raise _error(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "direct_model_runtime_unavailable",
                "Model runtime is not available.",
            )
        executor.submit(
            execute_direct_run,
            settings,
            accepted,
            request.app.state.agent_runtime_registry,
        )
    return StreamingResponse(
        _stream_run(settings=settings, accepted=accepted),
        status_code=status.HTTP_200_OK,
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
