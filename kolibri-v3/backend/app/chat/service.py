"""Durable Product Chat acceptance owned by the V3 Product/Data authority.

The browser request is converted into local product state and one immutable
Logical Home command in the same SQLite transaction.  Network delivery is
deliberately absent from this module: the independent product run worker owns
the outbox lease and survives an HTTP disconnect or restart.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Mapping

from ..attachment_service import (
    AttachmentConflictError,
    AttachmentMetadataError,
    AttachmentScopeError,
    bind_message_attachment_refs,
    parse_requested_attachment,
    resolve_requested_attachments,
)
from ..config import Settings
from ..database import transaction
from ..platform_authority import (
    PlatformDeveloperAuthorityError,
    require_persisted_platform_developer_authority,
    require_platform_developer_authority,
)
from ..product_entitlements import (
    CONSTRUCTION_ESTIMATES_ENTITLEMENT,
    ProductEntitlementError,
    require_product_entitlement,
)
from ..product_widgets import (
    is_estimate_generation_prompt,
    is_estimate_prompt,
)
from ..runtime_skills import (
    estimate_runtime_skill_plan,
    persist_runtime_skill_plan,
)
from ..schemas import UserSession
from ..trusted_agent_execution import (
    TrustedAgentExecutionError,
    select_trusted_agent_execution_binding,
)
from .errors import (
    ChatPolicyError,
    ChatRuntimeUnavailableError,
    IdempotencyConflictError,
    InvalidRunError,
    ProjectRuntimeBlockedError,
    ThreadHistoryConflictError,
)
from .models import (
    AgUiRunInput,
    MessageFeedbackInput,
    ThreadActionInput,
    canonical_run_payload,
    message_attachment_parts,
    message_text,
)

if TYPE_CHECKING:
    from .execution_adapter import PreparedChatExecution


_PUBLIC_ID = re.compile(
    r"^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$"
)
_DOCUMENT_SLOTS = (
    "source-data",
    "estimate",
    "commercial-proposal",
    "contract",
)
_ACCESS_POLICIES: dict[str, tuple[str | None, str, str, str | None]] = {
    "standard": (None, "read-only", "never", None),
    "auto": ("repository", "workspace-write", "on-request", "auto_review"),
    "full": ("repository", "danger-full-access", "never", None),
}
_DEVELOPER_RUN_CAPABILITY = "product.developer.run.execute.request"


@dataclass(frozen=True, slots=True)
class AcceptedRun:
    tenant_id: str
    project_id: str
    thread_id: str
    public_thread_id: str
    run_id: str
    public_run_id: str
    execution_mode: str
    execution_plane: str
    replayed: bool


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def typed_identity_id(prefix: str, raw_value: str) -> str:
    """Map a local UUID/identifier to a stable typed contract identifier."""

    if _PUBLIC_ID.fullmatch(raw_value):
        return raw_value
    try:
        suffix = uuid.UUID(raw_value).hex
    except (ValueError, AttributeError):
        suffix = hashlib.sha256(raw_value.encode("utf-8", "strict")).hexdigest()
    return f"{prefix}_{suffix}"


def sha256_text(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8', 'strict')).hexdigest()}"


def canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(
        dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def request_hash(run_input: AgUiRunInput) -> str:
    return sha256_text(canonical_json(canonical_run_payload(run_input)))


def storage_client_run_id(public_run_id: str, canonical_request_hash: str) -> str:
    """Scope transport run IDs to the exact immutable AG-UI request.

    assistant-ui may legitimately reuse a transport run while its local
    history projection catches up. Exact retries keep one durable run, while
    changed input cannot collide with the earlier request.
    """

    fingerprint = hashlib.sha256(
        (
            public_run_id
            + "\0"
            + canonical_request_hash
        ).encode("utf-8", "strict")
    ).hexdigest()
    return f"run_{fingerprint[:40]}"


def canonical_command_hash(command: Mapping[str, Any]) -> str:
    """Hash the command's semantic effect according to common contract v1."""

    identity = command["identity"]
    idempotency = command["idempotency"]
    effect = {
        "schema_id": command["schema_id"],
        "schema_version": command["schema_version"],
        "command_name": command["command_name"],
        "payload_schema_id": command["payload_schema_id"],
        "payload_schema_version": command["payload_schema_version"],
        "target_owner": command["target_owner"],
        "tenant_id": identity["tenant_id"],
        "user_id": identity["user_id"],
        "actor": identity["actor"],
        "subject_refs": identity["subject_refs"],
        "idempotency_scope": idempotency["scope"],
        "idempotency_scope_id": idempotency["scope_id"],
        "payload": command["payload"],
    }
    return sha256_text(canonical_json(effect))


def _title_from_prompt(prompt: str) -> str:
    collapsed = " ".join(prompt.split())
    if not collapsed:
        return "Новый проект"
    return collapsed[:80] + ("…" if len(collapsed) > 80 else "")


def _public_thread_id(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    thread_id: str,
) -> str:
    row = database.execute(
        """
        SELECT client_thread_id
        FROM chat_client_threads
        WHERE tenant_id = ? AND thread_id = ?
        LIMIT 1
        """,
        (tenant_id, thread_id),
    ).fetchone()
    return str(row["client_thread_id"]) if row is not None else thread_id


def resolve_thread(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    public_thread_id: str,
) -> sqlite3.Row | None:
    return database.execute(
        """
        SELECT t.*
        FROM chat_threads AS t
        LEFT JOIN chat_client_threads AS mapping
          ON mapping.tenant_id = t.tenant_id
         AND mapping.thread_id = t.id
        WHERE t.tenant_id = ?
          AND (t.id = ? OR mapping.client_thread_id = ?)
        LIMIT 1
        """,
        (tenant_id, public_thread_id, public_thread_id),
    ).fetchone()


def apply_thread_action(
    database: sqlite3.Connection,
    *,
    identity: UserSession,
    public_thread_id: str,
    action_input: ThreadActionInput,
) -> bool:
    """Apply one user-scoped thread-list action without deleting project data."""

    thread = resolve_thread(
        database,
        tenant_id=identity.tenant_id,
        public_thread_id=public_thread_id,
    )
    if thread is None:
        return False

    action = action_input.action
    changed_at = utc_now()
    thread_id = str(thread["id"])
    values = {
        "pin": ("pinned_at", changed_at),
        "unpin": ("pinned_at", None),
        "archive": ("archived_at", changed_at),
        "unarchive": ("archived_at", None),
        "remove": ("hidden_at", changed_at),
    }
    column, value = values[action]

    with transaction(database, immediate=True):
        database.execute(
            """
            INSERT INTO chat_thread_preferences (
                tenant_id, user_id, thread_id, pinned_at, archived_at,
                hidden_at, updated_at
            ) VALUES (?, ?, ?, NULL, NULL, NULL, ?)
            ON CONFLICT (tenant_id, user_id, thread_id) DO NOTHING
            """,
            (
                identity.tenant_id,
                identity.user_id,
                thread_id,
                changed_at,
            ),
        )
        if action == "remove":
            database.execute(
                """
                UPDATE chat_thread_preferences
                SET pinned_at = NULL,
                    archived_at = NULL,
                    hidden_at = ?,
                    updated_at = ?
                WHERE tenant_id = ? AND user_id = ? AND thread_id = ?
                """,
                (
                    changed_at,
                    changed_at,
                    identity.tenant_id,
                    identity.user_id,
                    thread_id,
                ),
            )
        else:
            database.execute(
                f"""
                UPDATE chat_thread_preferences
                SET {column} = ?, updated_at = ?
                WHERE tenant_id = ? AND user_id = ? AND thread_id = ?
                """,
                (
                    value,
                    changed_at,
                    identity.tenant_id,
                    identity.user_id,
                    thread_id,
                ),
            )
        database.execute(
            """
            INSERT INTO chat_thread_user_events (
                tenant_id, id, user_id, thread_id, action, created_at,
                metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                identity.tenant_id,
                new_id("event"),
                identity.user_id,
                thread_id,
                action,
                changed_at,
                canonical_json(
                    {
                        "projectId": str(thread["project_id"]),
                        "publicThreadId": public_thread_id,
                    }
                ),
            ),
        )
    return True


def submit_message_feedback(
    database: sqlite3.Connection,
    *,
    identity: UserSession,
    public_thread_id: str,
    public_message_id: str,
    feedback_input: MessageFeedbackInput,
) -> bool:
    """Persist one user's rating of an assistant message and its audit event."""

    thread = resolve_thread(
        database,
        tenant_id=identity.tenant_id,
        public_thread_id=public_thread_id,
    )
    if thread is None:
        return False

    message = database.execute(
        """
        SELECT id
        FROM chat_messages
        WHERE tenant_id = ?
          AND thread_id = ?
          AND role = 'assistant'
          AND (id = ? OR client_message_id = ?)
        LIMIT 1
        """,
        (
            identity.tenant_id,
            str(thread["id"]),
            public_message_id,
            public_message_id,
        ),
    ).fetchone()
    if message is None:
        # During a live AG-UI tool turn assistant-ui can temporarily expose
        # the TOOL_CALL_RESULT messageId as the action target. That transport
        # ID is durable in the event ledger but is not a second chat message;
        # resolve it to the run's canonical assistant_message_id.
        message = database.execute(
            """
            SELECT canonical.id
            FROM chat_run_events AS event
            JOIN chat_runs AS run
              ON run.tenant_id = event.tenant_id
             AND run.id = event.run_id
            JOIN chat_messages AS canonical
              ON canonical.tenant_id = run.tenant_id
             AND canonical.id = run.assistant_message_id
            WHERE event.tenant_id = ?
              AND run.thread_id = ?
              AND canonical.role = 'assistant'
              AND event.event_type = 'TOOL_CALL_RESULT'
              AND json_extract(event.event_json, '$.messageId') = ?
            ORDER BY event.sequence DESC
            LIMIT 1
            """,
            (
                identity.tenant_id,
                str(thread["id"]),
                public_message_id,
            ),
        ).fetchone()
    if message is None:
        return False

    changed_at = utc_now()
    message_id = str(message["id"])
    feedback_type = feedback_input.type
    with transaction(database, immediate=True):
        database.execute(
            """
            INSERT INTO chat_message_feedback (
                tenant_id, user_id, thread_id, message_id, feedback_type,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (tenant_id, user_id, message_id) DO UPDATE SET
                feedback_type = excluded.feedback_type,
                updated_at = excluded.updated_at
            """,
            (
                identity.tenant_id,
                identity.user_id,
                str(thread["id"]),
                message_id,
                feedback_type,
                changed_at,
                changed_at,
            ),
        )
        database.execute(
            """
            INSERT INTO chat_message_feedback_events (
                tenant_id, id, user_id, thread_id, message_id,
                feedback_type, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                identity.tenant_id,
                new_id("event"),
                identity.user_id,
                str(thread["id"]),
                message_id,
                feedback_type,
                changed_at,
            ),
        )
    return True


def _create_project_thread(
    database: sqlite3.Connection,
    *,
    identity: UserSession,
    client_thread_id: str,
    prompt: str,
    created_at: str,
) -> tuple[str, str]:
    project_id = new_id("project")
    object_id = new_id("object")
    thread_id = new_id("thread")
    goal_id = new_id("goal")
    # Logical Home's canonical ProjectCase projection derives this exact ID
    # from a newly created Goal.
    case_id = f"case_{goal_id}"
    title = _title_from_prompt(prompt)

    database.execute(
        """
        INSERT INTO projects (
            tenant_id, id, created_by_user_id, title, status,
            primary_thread_id, created_at, updated_at
        ) VALUES (?, ?, ?, ?, 'active', ?, ?, ?)
        """,
        (
            identity.tenant_id,
            project_id,
            identity.user_id,
            title,
            thread_id,
            created_at,
            created_at,
        ),
    )
    database.execute(
        """
        INSERT INTO construction_objects (
            tenant_id, id, project_id, name, name_source,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, 'placeholder', ?, ?)
        """,
        (
            identity.tenant_id,
            object_id,
            project_id,
            "Объект уточняется",
            created_at,
            created_at,
        ),
    )
    database.execute(
        """
        INSERT INTO chat_threads (
            tenant_id, id, project_id, kind, title, status,
            message_count, run_count, last_message_at, created_at, updated_at
        ) VALUES (?, ?, ?, 'primary', ?, 'regular', 0, 0, NULL, ?, ?)
        """,
        (
            identity.tenant_id,
            thread_id,
            project_id,
            title,
            created_at,
            created_at,
        ),
    )
    database.execute(
        """
        INSERT INTO chat_client_threads (
            tenant_id, client_thread_id, thread_id, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            identity.tenant_id,
            client_thread_id,
            thread_id,
            created_at,
            created_at,
        ),
    )
    for slot_type in _DOCUMENT_SLOTS:
        database.execute(
            """
            INSERT INTO document_slots (
                tenant_id, id, project_id, slot_type, version, status,
                content_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 1, 'empty', NULL, ?, ?)
            """,
            (
                identity.tenant_id,
                new_id("document"),
                project_id,
                slot_type,
                created_at,
                created_at,
            ),
        )
    database.execute(
        """
        INSERT INTO product_project_runtime (
            tenant_id, project_id, goal_id, case_id, goal_state,
            goal_error_code, created_at, updated_at
        ) VALUES (?, ?, ?, ?, 'pending', NULL, ?, ?)
        """,
        (
            identity.tenant_id,
            project_id,
            goal_id,
            case_id,
            created_at,
            created_at,
        ),
    )
    return project_id, thread_id


def _assert_thread_history(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    thread_id: str,
    supplied_message_ids: set[str],
) -> None:
    last = database.execute(
        """
        SELECT id, client_message_id
        FROM chat_messages
        WHERE tenant_id = ? AND thread_id = ?
        ORDER BY sequence DESC
        LIMIT 1
        """,
        (tenant_id, thread_id),
    ).fetchone()
    if last is None:
        return
    public_id = str(last["client_message_id"] or last["id"])
    if public_id not in supplied_message_ids:
        raise ThreadHistoryConflictError()


def _has_home_goal_initialization_evidence(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    project_id: str,
) -> bool:
    """Distinguish a Home-owned Goal from a local direct-runtime projection."""

    row = database.execute(
        """
        SELECT 1
        FROM product_runtime_exchanges AS exchange
        JOIN chat_runs AS run
          ON run.tenant_id = exchange.tenant_id
         AND run.id = exchange.run_id
        WHERE exchange.tenant_id = ?
          AND run.project_id = ?
          AND exchange.phase = 'goal_initialize'
          AND exchange.response_status BETWEEN 200 AND 299
          AND exchange.response_json IS NOT NULL
          AND exchange.response_hash IS NOT NULL
        LIMIT 1
        """,
        (tenant_id, project_id),
    ).fetchone()
    return row is not None


def _command_envelope(
    *,
    settings: Settings,
    identity: UserSession,
    created_at: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        authority = settings.require_product_authority_grant()
    except RuntimeError as exc:
        raise ChatRuntimeUnavailableError() from exc

    issued = datetime.fromisoformat(created_at)
    deadline = issued + timedelta(
        seconds=settings.product_run_command_deadline_seconds
    )
    tenant_id = typed_identity_id("tenant", identity.tenant_id)
    user_id = typed_identity_id("user", identity.user_id)
    envelope = {
        "schema_id": "kolibri.command",
        "schema_version": "1.0",
        "message_id": new_id("cmd"),
        "issued_at": issued.isoformat(),
        "deadline_at": deadline.isoformat(),
        "target_owner": "logical_home_control_plane",
        "identity": {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "actor": {
                "actor_id": typed_identity_id("actor", identity.user_id),
                "actor_type": "user",
            },
            "authority": authority.as_identity_authority(),
            "subject_refs": {
                "goal_id": None,
                "case_id": None,
                "task_id": None,
            },
        },
        "trace": {
            "trace_id": uuid.uuid4().hex,
            "span_id": uuid.uuid4().hex[:16],
            "parent_span_id": None,
            "correlation_id": new_id("correlation"),
            "causation_id": None,
        },
        "idempotency": {
            "key": "placeholder:idempotency",
            "scope": "aggregate",
            "scope_id": new_id("aggregate"),
            "canonical_request_hash": "sha256:" + ("0" * 64),
        },
    }
    return envelope, {"tenant_id": tenant_id, "user_id": user_id}


def _build_goal_initialize_command(
    *,
    settings: Settings,
    identity: UserSession,
    project_id: str,
    thread_id: str,
    run_id: str,
    input_message_id: str,
    goal_id: str,
    prompt: str,
    created_at: str,
) -> dict[str, Any]:
    command, typed = _command_envelope(
        settings=settings,
        identity=identity,
        created_at=created_at,
    )
    payload = {
        "schema_id": "kolibri.product.goal.initialize.command",
        "schema_version": "1.0",
        "tenant_id": typed["tenant_id"],
        "project_id": project_id,
        "thread_id": thread_id,
        "run_id": run_id,
        "input_message_id": input_message_id,
        "goal_id": goal_id,
        "prompt": prompt,
        "prompt_hash": sha256_text(prompt),
    }
    command.update(
        {
            "command_name": "product.goal.initialize",
            "payload_schema_id": "kolibri.product.goal.initialize.command",
            "payload_schema_version": "1.0",
            "payload": payload,
        }
    )
    command["identity"]["subject_refs"]["goal_id"] = goal_id
    command["trace"].update(
        {
            "correlation_id": run_id,
            "causation_id": input_message_id,
        }
    )
    command["idempotency"].update(
        {
            "key": f"product.goal.initialize:{goal_id}",
            "scope": "goal",
            "scope_id": goal_id,
        }
    )
    command["idempotency"]["canonical_request_hash"] = canonical_command_hash(
        command
    )
    return command


def build_product_run_command(
    *,
    settings: Settings,
    identity: UserSession,
    project_id: str,
    thread_id: str,
    run_id: str,
    input_message_id: str,
    goal_id: str,
    case_id: str,
    prompt: str,
    created_at: str,
    selected_profile: str | None = None,
    selected_model: str | None = None,
    selected_reasoning_effort: str | None = None,
    selected_service_tier: str | None = None,
    execution_mode: str = "standard",
    workspace_ref: str | None = None,
    access_mode: str | None = None,
    sandbox: str | None = None,
    approval_policy: str | None = None,
    reviewer: str | None = None,
    trusted_agent_profile_id: str | None = None,
    trusted_agent_profile_epoch: int | None = None,
    trusted_agent_workspace_binding_id: str | None = None,
    trusted_agent_workspace_binding_epoch: int | None = None,
) -> dict[str, Any]:
    if execution_mode == "developer":
        try:
            require_platform_developer_authority(identity)
        except PlatformDeveloperAuthorityError as exc:
            raise ChatPolicyError(
                exc.status_code,
                exc.code,
                exc.message,
            ) from exc
    command, typed = _command_envelope(
        settings=settings,
        identity=identity,
        created_at=created_at,
    )
    common_payload = {
        "tenant_id": typed["tenant_id"],
        "project_id": project_id,
        "thread_id": thread_id,
        "run_id": run_id,
        "input_message_id": input_message_id,
        "case_id": case_id,
        "goal_id": goal_id,
        "prompt": prompt,
        "prompt_hash": sha256_text(prompt),
    }
    runtime_profile = (
        selected_profile or identity.preferred_agent_profile.value
    )
    if execution_mode == "developer":
        trusted_binding_values = (
            trusted_agent_profile_id,
            trusted_agent_profile_epoch,
            trusted_agent_workspace_binding_id,
            trusted_agent_workspace_binding_epoch,
        )
        trusted_bound = all(
            value is not None for value in trusted_binding_values
        )
        if any(value is not None for value in trusted_binding_values) and not (
            trusted_bound
        ):
            raise ChatRuntimeUnavailableError()
        authority = command["identity"]["authority"]
        if (
            not identity.is_platform_owner
            or _DEVELOPER_RUN_CAPABILITY
            not in authority["capabilities"]
            or workspace_ref is None
            or access_mode is None
            or sandbox is None
            or approval_policy is None
        ):
            raise ChatRuntimeUnavailableError()
        payload_schema_id = (
            "kolibri.product.run.execute.v1_3.command"
            if trusted_bound
            else "kolibri.product.run.execute.v1_2.command"
        )
        payload_schema_version = "1.3" if trusted_bound else "1.2"
        payload = {
            "schema_id": payload_schema_id,
            "schema_version": payload_schema_version,
            **common_payload,
            "execution_mode": "developer",
            "runtime_profile": runtime_profile,
            "model": selected_model,
            "reasoning_effort": selected_reasoning_effort,
            "service_tier": selected_service_tier,
            "workspace_ref": workspace_ref,
            "access_mode": access_mode,
            "sandbox": sandbox,
            "approval_policy": approval_policy,
            "reviewer": reviewer,
            "requester_role": "owner",
        }
        if trusted_bound:
            payload.update(
                {
                    "trusted_agent_profile_id": trusted_agent_profile_id,
                    "trusted_agent_profile_epoch": (
                        trusted_agent_profile_epoch
                    ),
                    "trusted_agent_workspace_binding_id": (
                        trusted_agent_workspace_binding_id
                    ),
                    "trusted_agent_workspace_binding_epoch": (
                        trusted_agent_workspace_binding_epoch
                    ),
                }
            )
    else:
        payload_schema_id = "kolibri.product.run.execute.v1_1.command"
        payload_schema_version = "1.1"
        payload = {
            "schema_id": payload_schema_id,
            "schema_version": payload_schema_version,
            **common_payload,
            "preferred_agent_profile": runtime_profile,
            "preferred_model": selected_model,
            "preferred_reasoning_effort": selected_reasoning_effort,
        }
    command.update(
        {
            "command_name": "product.run.execute",
            "payload_schema_id": payload_schema_id,
            "payload_schema_version": payload_schema_version,
            "payload": payload,
        }
    )
    command["identity"]["subject_refs"].update(
        {"goal_id": goal_id, "case_id": case_id}
    )
    command["trace"].update(
        {
            "correlation_id": run_id,
            "causation_id": input_message_id,
        }
    )
    command["idempotency"].update(
        {
            "key": f"product.run.execute:{run_id}",
            "scope": "aggregate",
            "scope_id": run_id,
        }
    )
    command["idempotency"]["canonical_request_hash"] = canonical_command_hash(
        command
    )
    return command


def _insert_event(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    run_id: str,
    sequence: int,
    event: Mapping[str, Any],
    created_at: str,
) -> None:
    database.execute(
        """
        INSERT INTO chat_run_events (
            tenant_id, event_id, run_id, sequence, event_type,
            event_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            tenant_id,
            new_id("event"),
            run_id,
            sequence,
            str(event["type"]),
            canonical_json(event),
            created_at,
        ),
    )


def accept_run(
    database: sqlite3.Connection,
    *,
    settings: Settings,
    identity: UserSession,
    run_input: AgUiRunInput,
    prepared: PreparedChatExecution,
) -> AcceptedRun:
    """Atomically accept a strict AG-UI text run.

    Standard local-development chat may use the direct model runtime.
    The server-selected execution plane applies equally to standard and
    developer runs. HTTP callers must pass the prepared adapter decision so
    the exact catalog selection and policy are frozen with the run.
    """

    execution_mode = run_input.forwarded_props.execution_mode
    if execution_mode == "developer":
        try:
            require_platform_developer_authority(identity)
        except PlatformDeveloperAuthorityError as exc:
            raise ChatPolicyError(
                exc.status_code,
                exc.code,
                exc.message,
            ) from exc
    access_mode = run_input.forwarded_props.access_mode
    execution_plane = prepared.execution_plane
    if execution_plane not in {"direct", "home"}:
        raise ChatRuntimeUnavailableError()
    expected_plane = settings.chat_execution_plane(execution_mode)
    if execution_plane != expected_plane:
        raise ChatRuntimeUnavailableError()
    use_home_runtime = execution_plane == "home"
    if execution_mode == "developer":
        if use_home_runtime:
            try:
                developer_grant = settings.require_product_authority_grant()
            except RuntimeError as exc:
                raise ChatRuntimeUnavailableError() from exc
            if _DEVELOPER_RUN_CAPABILITY not in developer_grant.capabilities:
                raise ChatRuntimeUnavailableError()

    prompt = message_text(run_input.messages[-1])
    if is_estimate_prompt(prompt):
        try:
            require_product_entitlement(
                identity,
                CONSTRUCTION_ESTIMATES_ENTITLEMENT,
            )
        except ProductEntitlementError as exc:
            raise ChatPolicyError(
                exc.status_code,
                exc.code,
                exc.message,
            ) from exc
    input_message = run_input.messages[-1]
    incoming_hash = request_hash(run_input)
    created_at = utc_now()

    try:
        with transaction(database, immediate=True):
            platform_authority_epoch: int | None = None
            if execution_mode == "developer":
                try:
                    platform_authority_epoch = (
                        require_persisted_platform_developer_authority(
                            database,
                            user_id=identity.user_id,
                            tenant_id=identity.tenant_id,
                            expected_epoch=identity.platform_authority_epoch,
                        )
                    )
                except PlatformDeveloperAuthorityError as exc:
                    raise ChatPolicyError(
                        exc.status_code,
                        exc.code,
                        exc.message,
                    ) from exc
            created_project = False
            thread = resolve_thread(
                database,
                tenant_id=identity.tenant_id,
                public_thread_id=run_input.thread_id,
            )
            if thread is None:
                if len(prompt) > 20_000:
                    raise InvalidRunError(
                        "The first project message exceeds the Goal intake limit."
                    )
                created_project = True
                project_id, thread_id = _create_project_thread(
                    database,
                    identity=identity,
                    client_thread_id=run_input.thread_id,
                    prompt=prompt,
                    created_at=created_at,
                )
            else:
                project_id = str(thread["project_id"])
                thread_id = str(thread["id"])

            try:
                requested_attachment_refs = [
                    parse_requested_attachment(
                        data=part.source.value,
                        filename=part.metadata.filename,
                        mime_type=part.source.mime_type,
                    )
                    for part in message_attachment_parts(input_message)
                ]
                attachment_records = resolve_requested_attachments(
                    database,
                    tenant_id=identity.tenant_id,
                    user_id=identity.user_id,
                    project_id=project_id,
                    thread_id=thread_id,
                    requested=requested_attachment_refs,
                )
            except AttachmentMetadataError as exc:
                raise InvalidRunError(str(exc)) from exc
            except AttachmentScopeError as exc:
                raise ChatPolicyError(
                    404,
                    "attachment_not_found",
                    "An attachment is unavailable in this project.",
                ) from exc
            except AttachmentConflictError as exc:
                raise ChatPolicyError(
                    409,
                    "attachment_reference_conflict",
                    "Attachment metadata changed. Add the file again.",
                ) from exc

            stored_client_run_id = storage_client_run_id(
                run_input.run_id,
                incoming_hash,
            )
            replay = database.execute(
                """
                SELECT run.id, run.request_hash, run.input_message_id,
                       run.status,
                       COALESCE(context.execution_mode, 'standard')
                           AS execution_mode,
                       COALESCE(context.execution_plane, 'home')
                           AS execution_plane
                FROM chat_runs AS run
                LEFT JOIN chat_run_execution_contexts AS context
                  ON context.tenant_id = run.tenant_id
                 AND context.run_id = run.id
                WHERE run.tenant_id = ? AND run.thread_id = ?
                  AND run.client_run_id = ?
                LIMIT 1
                """,
                (identity.tenant_id, thread_id, stored_client_run_id),
            ).fetchone()
            if replay is None:
                # Compatibility for runs accepted before request-scoped storage
                # keys were introduced. A changed request deliberately does
                # not bind to the legacy row.
                replay = database.execute(
                    """
                    SELECT run.id, run.request_hash, run.input_message_id,
                           run.status,
                           COALESCE(context.execution_mode, 'standard')
                               AS execution_mode,
                           COALESCE(context.execution_plane, 'home')
                               AS execution_plane
                    FROM chat_runs AS run
                    LEFT JOIN chat_run_execution_contexts AS context
                      ON context.tenant_id = run.tenant_id
                     AND context.run_id = run.id
                    WHERE run.tenant_id = ? AND run.thread_id = ?
                      AND run.client_run_id = ? AND run.request_hash = ?
                    LIMIT 1
                    """,
                    (
                        identity.tenant_id,
                        thread_id,
                        run_input.run_id,
                        incoming_hash,
                    ),
                ).fetchone()
            if replay is not None:
                return AcceptedRun(
                    tenant_id=identity.tenant_id,
                    project_id=project_id,
                    thread_id=thread_id,
                    public_thread_id=_public_thread_id(
                        database,
                        tenant_id=identity.tenant_id,
                        thread_id=thread_id,
                    ),
                    run_id=str(replay["id"]),
                    public_run_id=run_input.run_id,
                    execution_mode=str(replay["execution_mode"]),
                    execution_plane=str(replay["execution_plane"]),
                    replayed=True,
                )

            if use_home_runtime:
                _assert_thread_history(
                    database,
                    tenant_id=identity.tenant_id,
                    thread_id=thread_id,
                    supplied_message_ids={
                        message.id for message in run_input.messages
                    },
                )

            force_goal_initialization = False
            runtime = database.execute(
                """
                SELECT goal_id, case_id, goal_state, goal_error_code
                FROM product_project_runtime
                WHERE tenant_id = ? AND project_id = ?
                LIMIT 1
                """,
                (identity.tenant_id, project_id),
            ).fetchone()
            if runtime is None:
                if len(prompt) > 20_000:
                    raise InvalidRunError(
                        "The first project message exceeds the Goal intake limit."
                    )
                # Existing threads may predate runtime migration.  They are
                # enrolled as pending and cannot bypass Goal initialization.
                goal_id = new_id("goal")
                case_id = f"case_{goal_id}"
                database.execute(
                    """
                    INSERT INTO product_project_runtime (
                        tenant_id, project_id, goal_id, case_id, goal_state,
                        goal_error_code, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, 'pending', NULL, ?, ?)
                    """,
                    (
                        identity.tenant_id,
                        project_id,
                        goal_id,
                        case_id,
                        created_at,
                        created_at,
                    ),
                )
                goal_state = "pending" if use_home_runtime else "initialized"
                if not use_home_runtime:
                    database.execute(
                        """
                        UPDATE product_project_runtime
                        SET goal_state = 'initialized',
                            goal_error_code = NULL,
                            updated_at = ?
                        WHERE tenant_id = ? AND project_id = ?
                        """,
                        (created_at, identity.tenant_id, project_id),
                    )
            else:
                goal_id = str(runtime["goal_id"])
                case_id = str(runtime["case_id"])
                goal_state = str(runtime["goal_state"])

            if (
                use_home_runtime
                and goal_state == "initialized"
                and not _has_home_goal_initialization_evidence(
                    database,
                    tenant_id=identity.tenant_id,
                    project_id=project_id,
                )
            ):
                # A standard direct run may have created only a local Product
                # projection. Developer execution cannot treat that as a
                # Logical Home Goal, so the same stable Goal is initialized
                # through the authoritative command before assignment.
                goal_state = "pending"
                force_goal_initialization = True
                database.execute(
                    """
                    UPDATE product_project_runtime
                    SET goal_state = 'pending',
                        goal_error_code = NULL,
                        updated_at = ?
                    WHERE tenant_id = ? AND project_id = ?
                    """,
                    (created_at, identity.tenant_id, project_id),
                )

            if not use_home_runtime and goal_state != "initialized":
                database.execute(
                    """
                    UPDATE product_project_runtime
                    SET goal_state = 'initialized',
                        goal_error_code = NULL,
                        updated_at = ?
                    WHERE tenant_id = ? AND project_id = ?
                    """,
                    (created_at, identity.tenant_id, project_id),
                )
                goal_state = "initialized"

            if (
                use_home_runtime
                and not created_project
                and not force_goal_initialization
                and goal_state == "pending"
            ):
                raise ProjectRuntimeBlockedError(
                    "project_goal_initializing",
                    "Project initialization is still in progress.",
                )
            if use_home_runtime and goal_state == "failed":
                raise ProjectRuntimeBlockedError(
                    "project_goal_initialization_failed",
                    "Project initialization must be retried before sending.",
                )

            run_id = new_id("run")
            selected_profile = prepared.runtime_profile
            estimate_owned_model_policy = is_estimate_generation_prompt(prompt)
            selected_model = prepared.model_id
            selected_reasoning_effort = prepared.reasoning_effort
            selected_service_tier = prepared.service_tier
            # This second, transactional decision is mandatory even for
            # internal callers that do not use the HTTP preparation adapter.
            # It also happens after exact-replay resolution, so retries do not
            # consume or get rejected by the monthly quota.
            from ..platform_admin import (
                PlatformPolicyError,
                enforce_chat_access_policy,
            )

            try:
                enforce_chat_access_policy(
                    database,
                    identity=identity,
                    execution_mode=execution_mode,
                    runtime_profile=selected_profile,
                    model_id=selected_model,
                )
            except PlatformPolicyError as exc:
                raise ChatPolicyError(
                    exc.status_code,
                    exc.code,
                    exc.message,
                ) from exc
            stored_input = database.execute(
                """
                SELECT id, content_text
                FROM chat_messages
                WHERE tenant_id = ? AND thread_id = ?
                  AND client_message_id = ? AND role = 'user'
                LIMIT 1
                """,
                (identity.tenant_id, thread_id, input_message.id),
            ).fetchone()
            inserted_input = stored_input is None
            if stored_input is not None:
                if str(stored_input["content_text"]) != prompt:
                    raise InvalidRunError(
                        "A message ID cannot be reused with different content."
                    )
                input_message_id = str(stored_input["id"])
            else:
                sequence_row = database.execute(
                    """
                    SELECT COALESCE(MAX(sequence), 0) AS value
                    FROM chat_messages
                    WHERE tenant_id = ? AND thread_id = ?
                    """,
                    (identity.tenant_id, thread_id),
                ).fetchone()
                message_sequence = int(sequence_row["value"]) + 1
                input_message_id = new_id("message")
                database.execute(
                    """
                    INSERT INTO chat_messages (
                        tenant_id, id, project_id, thread_id, sequence,
                        client_message_id, run_id, role, content_text,
                        created_by_user_id, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'user', ?, ?, ?)
                    """,
                    (
                        identity.tenant_id,
                        input_message_id,
                        project_id,
                        thread_id,
                        message_sequence,
                        input_message.id,
                        run_id,
                        prompt,
                        identity.user_id,
                        created_at,
                    ),
                )
            try:
                bind_message_attachment_refs(
                    database,
                    tenant_id=identity.tenant_id,
                    message_id=input_message_id,
                    records=attachment_records,
                    created_at=created_at,
                )
            except AttachmentConflictError as exc:
                raise ChatPolicyError(
                    409,
                    "attachment_reference_conflict",
                    "Message attachments do not match the original send.",
                ) from exc
            database.execute(
                """
                INSERT INTO chat_runs (
                    tenant_id, id, project_id, thread_id, client_run_id,
                    request_hash, input_message_id, assistant_message_id,
                    requested_by_user_id, selected_profile, status, outcome,
                    last_event_sequence, error_code, heartbeat_at, created_at,
                    updated_at, finished_at
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, 'running', NULL,
                    1, NULL, ?, ?, ?, NULL
                )
                """,
                (
                    identity.tenant_id,
                    run_id,
                    project_id,
                    thread_id,
                    stored_client_run_id,
                    incoming_hash,
                    input_message_id,
                    identity.user_id,
                    selected_profile,
                    created_at,
                    created_at,
                    created_at,
                ),
            )
            legacy_developer_access = (
                execution_mode == "developer"
                and "access_mode"
                not in run_input.forwarded_props.model_fields_set
            )
            frozen_access_policy = (
                (
                    "repository",
                    "workspace-write",
                    "never",
                    None,
                )
                if legacy_developer_access
                else _ACCESS_POLICIES[access_mode]
            )
            trusted_agent_binding = None
            if execution_mode == "developer":
                if platform_authority_epoch is None:
                    raise ChatPolicyError(
                        403,
                        "owner_required",
                        "Owner access is required for developer agent mode.",
                    )
                try:
                    trusted_agent_binding = (
                        select_trusted_agent_execution_binding(
                            database,
                            tenant_id=identity.tenant_id,
                            user_id=identity.user_id,
                            authority_epoch=platform_authority_epoch,
                            runtime_profile=selected_profile,
                            access_mode=access_mode,
                            sandbox_profile=frozen_access_policy[1],
                            approval_policy=frozen_access_policy[2],
                            approvals_reviewer=frozen_access_policy[3],
                        )
                    )
                except TrustedAgentExecutionError as exc:
                    raise ChatPolicyError(
                        409,
                        exc.code,
                        exc.message,
                    ) from exc
            database.execute(
                """
                INSERT INTO chat_run_execution_contexts (
                    tenant_id, run_id, execution_mode, execution_plane,
                    platform_authority_epoch, access_mode,
                    access_policy_version, authority_role, authority_user_id,
                    workspace_ref, sandbox_profile, approval_policy,
                    approvals_reviewer, model_id, reasoning_effort,
                    service_tier, created_at,
                    trusted_agent_profile_id,
                    trusted_agent_profile_epoch,
                    trusted_agent_workspace_binding_id,
                    trusted_agent_workspace_binding_epoch
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?
                )
                """,
                (
                    identity.tenant_id,
                    run_id,
                    execution_mode,
                    execution_plane,
                    platform_authority_epoch,
                    access_mode,
                    1 if legacy_developer_access else 2,
                    identity.role.value,
                    identity.user_id,
                    frozen_access_policy[0],
                    frozen_access_policy[1],
                    frozen_access_policy[2],
                    frozen_access_policy[3],
                    selected_model,
                    selected_reasoning_effort,
                    selected_service_tier,
                    created_at,
                    (
                        trusted_agent_binding.profile_id
                        if trusted_agent_binding is not None
                        else None
                    ),
                    (
                        trusted_agent_binding.profile_epoch
                        if trusted_agent_binding is not None
                        else None
                    ),
                    (
                        trusted_agent_binding.workspace_binding_id
                        if trusted_agent_binding is not None
                        else None
                    ),
                    (
                        trusted_agent_binding.workspace_binding_epoch
                        if trusted_agent_binding is not None
                        else None
                    ),
                ),
            )
            # A runtime skill is reviewed server-owned guidance, not a
            # browser-selected prompt and not an AgentAssignment.  Recording
            # it with the accepted run freezes the exact constraints used by
            # both supported model profiles and keeps reconnect/replay stable.
            if (
                estimate_owned_model_policy
                and execution_mode != "developer"
            ):
                persist_runtime_skill_plan(
                    database,
                    tenant_id=identity.tenant_id,
                    run_id=run_id,
                    plan=estimate_runtime_skill_plan(),
                    created_at=created_at,
                )
            _insert_event(
                database,
                tenant_id=identity.tenant_id,
                run_id=run_id,
                sequence=1,
                event={
                    "type": "RUN_STARTED",
                    "threadId": run_input.thread_id,
                    "runId": run_input.run_id,
                },
                created_at=created_at,
            )

            if use_home_runtime:
                if goal_state == "initialized":
                    command = build_product_run_command(
                        settings=settings,
                        identity=identity,
                        project_id=project_id,
                        thread_id=thread_id,
                        run_id=run_id,
                        input_message_id=input_message_id,
                        goal_id=goal_id,
                        case_id=case_id,
                        prompt=prompt,
                        created_at=created_at,
                        selected_profile=selected_profile,
                        selected_model=selected_model,
                        selected_reasoning_effort=(
                            selected_reasoning_effort
                        ),
                        selected_service_tier=selected_service_tier,
                        execution_mode=execution_mode,
                        workspace_ref=frozen_access_policy[0],
                        access_mode=access_mode,
                        sandbox=frozen_access_policy[1],
                        approval_policy=frozen_access_policy[2],
                        reviewer=frozen_access_policy[3],
                        trusted_agent_profile_id=(
                            trusted_agent_binding.profile_id
                            if trusted_agent_binding is not None
                            else None
                        ),
                        trusted_agent_profile_epoch=(
                            trusted_agent_binding.profile_epoch
                            if trusted_agent_binding is not None
                            else None
                        ),
                        trusted_agent_workspace_binding_id=(
                            trusted_agent_binding.workspace_binding_id
                            if trusted_agent_binding is not None
                            else None
                        ),
                        trusted_agent_workspace_binding_epoch=(
                            trusted_agent_binding.workspace_binding_epoch
                            if trusted_agent_binding is not None
                            else None
                        ),
                    )
                    command_kind = "product.run.execute"
                    phase = "run_execute"
                else:
                    command = _build_goal_initialize_command(
                        settings=settings,
                        identity=identity,
                        project_id=project_id,
                        thread_id=thread_id,
                        run_id=run_id,
                        input_message_id=input_message_id,
                        goal_id=goal_id,
                        prompt=prompt,
                        created_at=created_at,
                    )
                    command_kind = "product.goal.initialize"
                    phase = "goal_required"
                command_json = canonical_json(command)
                outbox_id = new_id("outbox")
                database.execute(
                    """
                    INSERT INTO product_run_outbox (
                        tenant_id, id, run_id, command_kind, phase, state,
                        command_json, command_hash, attempts, max_attempts,
                        available_at, lease_owner, lease_token, lease_until,
                        fencing_token, last_error_code, created_at, updated_at,
                        completed_at
                    ) VALUES (
                        ?, ?, ?, ?, ?, 'queued',
                        ?, ?, 0, ?, ?, NULL, NULL, NULL, 0, NULL, ?, ?, NULL
                    )
                    """,
                    (
                        identity.tenant_id,
                        outbox_id,
                        run_id,
                        command_kind,
                        phase,
                        command_json,
                        sha256_text(command_json),
                        (
                            1
                            if (
                                execution_mode == "developer"
                                and command_kind == "product.run.execute"
                            )
                            else settings.product_run_max_attempts
                        ),
                        created_at,
                        created_at,
                        created_at,
                    ),
                )
            else:
                database.execute(
                    """
                    INSERT INTO direct_run_outbox (
                        tenant_id, run_id, public_thread_id, public_run_id,
                        state, lease_owner, lease_token, lease_until,
                        fencing_token, last_error_code, created_at, updated_at,
                        completed_at
                    ) VALUES (
                        ?, ?, ?, ?, 'queued', NULL, NULL, NULL,
                        0, NULL, ?, ?, NULL
                    )
                    """,
                    (
                        identity.tenant_id,
                        run_id,
                        run_input.thread_id,
                        run_input.run_id,
                        created_at,
                        created_at,
                    ),
                )
            database.execute(
                """
                UPDATE chat_threads
                SET message_count = message_count + ?,
                    run_count = run_count + 1,
                    last_message_at = ?,
                    updated_at = ?
                WHERE tenant_id = ? AND id = ?
                """,
                (
                    1 if inserted_input else 0,
                    created_at,
                    created_at,
                    identity.tenant_id,
                    thread_id,
                ),
            )
            database.execute(
                """
                UPDATE projects
                SET updated_at = ?
                WHERE tenant_id = ? AND id = ?
                """,
                (created_at, identity.tenant_id, project_id),
            )
    except sqlite3.IntegrityError as exc:
        # Keep SQL details out of the HTTP surface.  Unique client run/message
        # collisions are conflicts rather than a second side effect.
        raise IdempotencyConflictError() from exc

    return AcceptedRun(
        tenant_id=identity.tenant_id,
        project_id=project_id,
        thread_id=thread_id,
        public_thread_id=run_input.thread_id,
        run_id=run_id,
        public_run_id=run_input.run_id,
        execution_mode=execution_mode,
        execution_plane=execution_plane,
        replayed=False,
    )


def public_thread_id(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    thread_id: str,
) -> str:
    return _public_thread_id(
        database,
        tenant_id=tenant_id,
        thread_id=thread_id,
    )


__all__ = [
    "AcceptedRun",
    "accept_run",
    "build_product_run_command",
    "canonical_command_hash",
    "canonical_json",
    "new_id",
    "public_thread_id",
    "resolve_thread",
    "sha256_text",
    "typed_identity_id",
    "utc_now",
]
