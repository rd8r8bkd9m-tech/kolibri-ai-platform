"""Small direct provider runtime for the local Kolibri V3 product chat."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import re
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Protocol
from urllib.parse import urlsplit
import uuid

import httpx
from pydantic import ValidationError

from .agent_runtime import (
    AgentAccessPolicy,
    AgentExecutionConfiguration,
    AgentModelSelection,
    AgentRuntimeCapabilities,
    AgentRuntimeDescriptor,
    AgentRuntimeError,
    AgentRuntimeMessage,
    AgentRuntimeRegistry,
    AgentRuntimeRequest,
    AgentRuntimeResult,
    AgentToolCall,
    AgentWorkspace,
    DelegatingAgentRuntime,
)
from .codex_app_server import (
    CodexAppServerAuthenticationError,
    CodexAppServerError,
    CodexAppServerRuntime,
)
from .config import Settings
from .database import connect_database, transaction
from .direct_run_outbox import DirectRunClaim, DirectRunStore
from .estimate_artifact import (
    ESTIMATE_PROPOSAL_SCHEMA,
    GeneratedEstimateProposal,
    estimate_proposal_instructions,
    parse_generated_estimate,
)
from .estimate_intake import (
    PLASTERING_INTAKE_SCHEMA,
    PlasteringIntake,
    normalize_plastering_intake,
    parse_plastering_intake,
    plastering_intake_instructions,
)
from .generated_image_artifacts import (
    GeneratedImageArtifactError,
    PreparedGeneratedImageArtifact,
    persist_generated_image_artifact,
    prepare_generated_image_artifact,
)
from .image_generation import (
    IMAGE_GENERATION_CAPABILITY_ID,
    IMAGE_GENERATION_CLARIFICATION,
    ImageGenerationError,
    ImageGenerationProvider,
    ImageGenerationRequest,
    UnavailableImageGenerationProvider,
    resolve_image_prompt,
)
from .local_provider_authority import (
    LocalProviderAuthorityError,
    load_mimo_key,
)
from .mimo_client import MimoClientRuntime
from .mimo_developer_runtime import (
    MimoDeveloperServerRuntime,
    MimoDeveloperRuntimeError,
)
from .product_widgets import (
    ProductWidget,
    is_estimate_generation_prompt,
    materialize_engine_estimate_widget,
    try_prepare_product_widget,
)
from .runtime_skills import (
    RuntimeSkillError,
    RuntimeSkillPlan,
    estimate_runtime_skill_plan,
    load_runtime_skill_plan,
    persist_runtime_skill_plan,
)
from .trusted_agent_execution import (
    TrustedAgentExecutionError,
    validate_frozen_trusted_agent_execution_binding,
)
from .weather_service import (
    WeatherServiceError,
    get_weather,
    try_parse_weather_query,
)

logger = logging.getLogger(__name__)


class DirectModelError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class ModelToolCall:
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ModelTurn:
    text: str | None = None
    tool_call: ModelToolCall | None = None


GET_WEATHER_TOOL = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": (
            "Получить текущую погоду и прогноз для любого населённого пункта. "
            "Используй этот инструмент для вопросов о погоде вместо ответа по памяти."
        ),
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "location": {
                    "type": "string",
                    "description": "Нормальное название запрошенного населённого пункта.",
                    "minLength": 1,
                    "maxLength": 160,
                },
                "forecastDays": {
                    "type": "integer",
                    "description": (
                        "Число дней прогноза от 1 до 7. "
                        "Если пользователь не указал период, передай 5."
                    ),
                    "minimum": 1,
                    "maximum": 7,
                },
            },
            "required": ["location", "forecastDays"],
        },
    },
}

CODEX_TURN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "type": {"type": "string", "enum": ["answer", "tool"]},
        "text": {"type": "string"},
        "toolName": {"type": "string", "enum": ["", "get_weather"]},
        "location": {"type": "string", "maxLength": 160},
        "forecastDays": {"type": "integer", "minimum": 0, "maximum": 7},
    },
    "required": ["type", "text", "toolName", "location", "forecastDays"],
}

CODEX_TURN_INSTRUCTIONS = """
Ты — AI-модель внутри чата Kolibri. Для каждого запроса выбери ровно одно:
1. type=tool, toolName=get_weather — если пользователю нужны текущая погода,
   температура, осадки или прогноз. Передай нормальное название любого
   населённого пункта в location и 1–7 дней в forecastDays. Если период не
   указан, передай 5. Не отвечай о текущей погоде по памяти.
2. type=answer — для остальных запросов. Запиши обычный полезный ответ в text,
   а toolName/location оставь пустыми и forecastDays=0.
Не запускай команды, не читай файлы и не изменяй систему.
Источником истории является только переданный Kolibri снимок разговора.
Не раскрывай внутренний JSON: верни его строго по переданной output schema.
""".strip()

AGENT_CHAT_INSTRUCTIONS = """
Ты — AI-ассистент Kolibri. Отвечай пользователю прямо, полезно и кратко на
языке его сообщения. Возвращай только обычный текст ответа или Markdown:
никакого служебного JSON и никаких внутренних комментариев.
Не запускай команды, не читай файлы и не изменяй систему.
Источником истории является только переданный Kolibri снимок разговора.
Актуальную погоду Kolibri обрабатывает отдельным сервисом до вызова модели.
""".strip()


_SMALLTALK_GREETING = re.compile(
    r"(?iu)^(?:привет|здравствуй(?:те)?|добрый\s+(?:день|вечер|утро)|hi|hello)\b"
)
_CAPABILITY_WORDS = re.compile(
    r"(?iu)\b(?:что\s+)?(?:умеешь|можешь|можешь\s+делать|твои\s+возможности|"
    r"возможности|help|помощь)\b"
)
_SIMPLE_ARITHMETIC = re.compile(r"^\s*(-?\d{1,12})\s*([+\-*/])\s*(-?\d{1,12})\s*$")


def _try_local_conversational_answer(prompt: str) -> str | None:
    """Answer tiny context-breaking turns without replaying product workflows.

    These turns are intentionally resolved from the latest user message only.
    They must not inspect prior estimate context or open/generate artifacts.
    """

    stripped = " ".join(prompt.strip().split())
    if not stripped:
        return None

    arithmetic = _SIMPLE_ARITHMETIC.fullmatch(stripped.replace(",", "."))
    if arithmetic is not None:
        left = int(arithmetic.group(1))
        operator = arithmetic.group(2)
        right = int(arithmetic.group(3))
        if operator == "+":
            return str(left + right)
        if operator == "-":
            return str(left - right)
        if operator == "*":
            return str(left * right)
        if right == 0:
            return "На ноль делить нельзя."
        quotient = left / right
        return str(int(quotient)) if quotient.is_integer() else f"{quotient:.10g}"

    lower = stripped.lower()
    has_greeting = _SMALLTALK_GREETING.search(lower) is not None
    asks_capabilities = _CAPABILITY_WORDS.search(lower) is not None
    if has_greeting and asks_capabilities:
        return (
            "Привет! Я Kolibri/MiMo. Могу отвечать на вопросы, считать, "
            "помогать с проектами и строительными сметами, готовить "
            "технологические карты, документы и проверяемые артефакты."
        )
    if has_greeting and len(stripped) <= 40:
        return "Привет! Чем могу помочь?"
    if asks_capabilities and len(stripped) <= 120:
        return (
            "Могу отвечать на вопросы, считать, помогать с проектами, "
            "сметами, технологическими картами, документами и проверками."
        )
    return None


AGENT_DEVELOPER_INSTRUCTIONS = """
Ты — встроенный агент-разработчик KolibriAI. Пользователь уже прошёл
серверную проверку роли владельца. Работай как практический Codex внутри
переданного репозитория: исследуй реальный execution path, редактируй только
нужные файлы, запускай подходящие локальные тесты и показывай проверяемый
результат.

Обязательно соблюдай AGENTS.md и вложенные инструкции репозитория. Не читай и
не публикуй значения ключей, cookies, токенов или private keys в ответе.
Владелец явно подтвердил полный локальный доступ для этой development-сессии.
У тебя есть обычные встроенные инструменты Codex и unrestricted shell; реально
выполняй поставленную задачу, а не отвечай, что shell или filesystem
недоступны.

Не выводи chain-of-thought. В ходе работы используй обычные инструменты Codex.
В финале кратко перечисли изменённые файлы, существенные решения, выполненные
проверки и оставшиеся ограничения. Для небольших изменений покажи уместный
фрагмент кода или diff в Markdown.
""".strip()

_SENSITIVE_ACTIVITY = re.compile(
    r"(?i)(authorization:\s*bearer\s+\S+|"
    r"(?:api[_-]?key|token|password|secret)\s*[=:]\s*\S+|"
    r"sk-[A-Za-z0-9_-]{12,})"
)
_SENSITIVE_PATH_PART = re.compile(
    r"(?i)(^|[/.])(?:\.env(?:\.|$)|\.ssh(?:/|$)|"
    r"credentials?(?:[./_-]|$)|secrets?(?:[./_-]|$)|"
    r"tokens?(?:[./_-]|$))"
)


class AcceptedRunLike(Protocol):
    tenant_id: str
    project_id: str
    thread_id: str
    public_thread_id: str
    run_id: str
    public_run_id: str
    execution_mode: str


def _validate_direct_trusted_agent_binding(
    database: sqlite3.Connection,
    run: sqlite3.Row,
    *,
    tenant_id: str,
) -> None:
    frozen_authority_epoch = run["platform_authority_epoch"]
    if frozen_authority_epoch is None:
        raise DirectModelError(
            "owner_required",
            "Owner access is required for developer agent mode.",
        )
    try:
        validate_frozen_trusted_agent_execution_binding(
            database,
            tenant_id=tenant_id,
            user_id=str(run["requested_by_user_id"]),
            authority_epoch=int(frozen_authority_epoch),
            runtime_profile=str(run["selected_profile"]),
            access_mode=str(run["access_mode"]),
            sandbox_profile=str(run["sandbox_profile"]),
            approval_policy=str(run["approval_policy"]),
            approvals_reviewer=(
                None
                if run["approvals_reviewer"] is None
                else str(run["approvals_reviewer"])
            ),
            profile_id=run["trusted_agent_profile_id"],
            profile_epoch=run["trusted_agent_profile_epoch"],
            workspace_binding_id=(
                run["trusted_agent_workspace_binding_id"]
            ),
            workspace_binding_epoch=(
                run["trusted_agent_workspace_binding_epoch"]
            ),
        )
    except TrustedAgentExecutionError as exc:
        raise DirectModelError(exc.code, exc.message) from exc


def _redact_developer_text(value: object, *, limit: int) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return _SENSITIVE_ACTIVITY.sub("[REDACTED]", text)[:limit]


def _developer_path(
    value: object,
    *,
    workspace_root: Path,
) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        path = Path(raw)
        resolved = (
            path.resolve() if path.is_absolute() else (workspace_root / path).resolve()
        )
        relative = resolved.relative_to(workspace_root)
    except (OSError, ValueError):
        return "[outside-workspace]"
    return relative.as_posix() or "."


def _developer_activity_payload(
    item: dict[str, Any],
    *,
    phase: str,
    workspace_root: Path,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    item_type = str(item.get("type") or "")
    if item_type == "commandExecution":
        arguments = {
            "command": _redact_developer_text(
                item.get("command"),
                limit=800,
            ),
            "cwd": _developer_path(
                item.get("cwd"),
                workspace_root=workspace_root,
            ),
        }
        result = {
            "status": _redact_developer_text(
                item.get("status"),
                limit=40,
            ),
            "exitCode": item.get("exitCode"),
            "durationMs": item.get("durationMs"),
            "output": _redact_developer_text(
                item.get("output"),
                limit=12_000,
            ),
        }
        return "developer_command", arguments, result

    changes: list[dict[str, str]] = []
    for raw_change in item.get("changes") or []:
        if not isinstance(raw_change, dict) or len(changes) >= 40:
            continue
        path = _developer_path(
            raw_change.get("path"),
            workspace_root=workspace_root,
        )
        sensitive = bool(_SENSITIVE_PATH_PART.search(path))
        changes.append(
            {
                "path": path,
                "kind": _redact_developer_text(
                    raw_change.get("kind"),
                    limit=40,
                ),
                "diff": (
                    "[REDACTED: sensitive path]"
                    if sensitive
                    else _redact_developer_text(
                        raw_change.get("diff"),
                        limit=12_000,
                    )
                )
                if phase == "completed"
                else "",
            }
        )
    arguments = {
        "files": [
            {"path": change["path"], "kind": change["kind"]} for change in changes
        ]
    }
    result = {
        "status": _redact_developer_text(item.get("status"), limit=40),
        "changes": changes,
    }
    return "developer_file_change", arguments, result


class _TextRunStream:
    """Persist model deltas as resumable AG-UI events while the turn runs."""

    def __init__(
        self,
        settings: Settings,
        accepted: AcceptedRunLike,
        *,
        provider: str,
    ) -> None:
        self.settings = settings
        self.accepted = accepted
        self.provider = provider
        self.message_id = new_id("message")
        self.started = False
        self.text = ""
        self._started_at = time.monotonic()
        self._lock = threading.Lock()

    def append(self, delta: str) -> None:
        if not delta:
            return
        with self._lock:
            database = connect_database(self.settings.database_url)
            now = utc_now()
            try:
                with transaction(database, immediate=True):
                    run = database.execute(
                        """
                        SELECT last_event_sequence, status
                        FROM chat_runs
                        WHERE tenant_id = ? AND id = ?
                        """,
                        (
                            self.accepted.tenant_id,
                            self.accepted.run_id,
                        ),
                    ).fetchone()
                    if run is None or str(run["status"]) != "running":
                        return
                    first = int(run["last_event_sequence"]) + 1
                    events: list[dict[str, Any]] = []
                    if not self.started:
                        events.append(
                            {
                                "type": "TEXT_MESSAGE_START",
                                "messageId": self.message_id,
                                "role": "assistant",
                            }
                        )
                    events.append(
                        {
                            "type": "TEXT_MESSAGE_CONTENT",
                            "messageId": self.message_id,
                            "delta": delta,
                        }
                    )
                    for offset, event in enumerate(events):
                        _insert_event(
                            database,
                            tenant_id=self.accepted.tenant_id,
                            run_id=self.accepted.run_id,
                            sequence=first + offset,
                            event=event,
                            created_at=now,
                        )
                    database.execute(
                        """
                        UPDATE chat_runs
                        SET last_event_sequence = ?, heartbeat_at = ?,
                            updated_at = ?
                        WHERE tenant_id = ? AND id = ?
                        """,
                        (
                            first + len(events) - 1,
                            now,
                            now,
                            self.accepted.tenant_id,
                            self.accepted.run_id,
                        ),
                    )
                first_delta = not self.started
                self.started = True
                self.text += delta
                if first_delta:
                    logger.info(
                        "Direct model first delta provider=%s run=%s ttft_ms=%d",
                        self.provider,
                        self.accepted.public_run_id,
                        round((time.monotonic() - self._started_at) * 1000),
                    )
            finally:
                database.close()

    def elapsed_ms(self) -> int:
        return round((time.monotonic() - self._started_at) * 1000)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _insert_event(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    run_id: str,
    sequence: int,
    event: dict[str, Any],
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
            json.dumps(
                event,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ),
            created_at,
        ),
    )


def _start_tool_stage(
    settings: Settings,
    accepted: AcceptedRunLike,
    *,
    tool_name: str,
    arguments: dict[str, Any],
) -> str:
    tool_call_id = new_id("tool")
    parent_message_id = new_id("message")
    arguments_json = json.dumps(
        arguments,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    database = connect_database(settings.database_url)
    now = utc_now()
    try:
        with transaction(database, immediate=True):
            run = database.execute(
                """
                SELECT last_event_sequence, status
                FROM chat_runs
                WHERE tenant_id = ? AND id = ?
                LIMIT 1
                """,
                (accepted.tenant_id, accepted.run_id),
            ).fetchone()
            if run is None or str(run["status"]) != "running":
                return tool_call_id
            first = int(run["last_event_sequence"]) + 1
            events = (
                {
                    "type": "TOOL_CALL_START",
                    "toolCallId": tool_call_id,
                    "toolCallName": tool_name,
                    "parentMessageId": parent_message_id,
                },
                {
                    "type": "TOOL_CALL_ARGS",
                    "toolCallId": tool_call_id,
                    "delta": arguments_json,
                },
                {
                    "type": "TOOL_CALL_END",
                    "toolCallId": tool_call_id,
                },
            )
            for offset, event in enumerate(events):
                _insert_event(
                    database,
                    tenant_id=accepted.tenant_id,
                    run_id=accepted.run_id,
                    sequence=first + offset,
                    event=event,
                    created_at=now,
                )
            database.execute(
                """
                UPDATE chat_runs
                SET last_event_sequence = ?, heartbeat_at = ?, updated_at = ?
                WHERE tenant_id = ? AND id = ?
                """,
                (
                    first + len(events) - 1,
                    now,
                    now,
                    accepted.tenant_id,
                    accepted.run_id,
                ),
            )
    finally:
        database.close()
    return tool_call_id


def _finish_tool_stage(
    settings: Settings,
    accepted: AcceptedRunLike,
    *,
    tool_call_id: str,
    result: dict[str, Any],
) -> None:
    database = connect_database(settings.database_url)
    now = utc_now()
    try:
        with transaction(database, immediate=True):
            run = database.execute(
                """
                SELECT last_event_sequence, status
                FROM chat_runs
                WHERE tenant_id = ? AND id = ?
                LIMIT 1
                """,
                (accepted.tenant_id, accepted.run_id),
            ).fetchone()
            if run is None or str(run["status"]) != "running":
                return
            sequence = int(run["last_event_sequence"]) + 1
            _insert_event(
                database,
                tenant_id=accepted.tenant_id,
                run_id=accepted.run_id,
                sequence=sequence,
                event={
                    "type": "TOOL_CALL_RESULT",
                    "messageId": new_id("message"),
                    "toolCallId": tool_call_id,
                    "content": json.dumps(
                        result,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                        allow_nan=False,
                    ),
                    "role": "tool",
                },
                created_at=now,
            )
            database.execute(
                """
                UPDATE chat_runs
                SET last_event_sequence = ?, heartbeat_at = ?, updated_at = ?
                WHERE tenant_id = ? AND id = ?
                """,
                (
                    sequence,
                    now,
                    now,
                    accepted.tenant_id,
                    accepted.run_id,
                ),
            )
    finally:
        database.close()


def _complete_tool_stage(
    settings: Settings,
    accepted: AcceptedRunLike,
    *,
    tool_name: str,
    arguments: dict[str, Any],
    result: dict[str, Any],
) -> None:
    tool_call_id = _start_tool_stage(
        settings,
        accepted,
        tool_name=tool_name,
        arguments=arguments,
    )
    _finish_tool_stage(
        settings,
        accepted,
        tool_call_id=tool_call_id,
        result=result,
    )


def _history(
    database: sqlite3.Connection,
    accepted: AcceptedRunLike,
) -> list[dict[str, str]]:
    rows = database.execute(
        """
        SELECT message.role, message.content_text
        FROM chat_messages AS message
        JOIN chat_runs AS run
          ON run.tenant_id = message.tenant_id
         AND run.thread_id = message.thread_id
         AND run.id = ?
        JOIN chat_messages AS input
          ON input.tenant_id = run.tenant_id
         AND input.id = run.input_message_id
        WHERE message.tenant_id = ?
          AND message.thread_id = ?
          AND message.sequence <= input.sequence
        ORDER BY message.sequence DESC
        LIMIT 60
        """,
        (accepted.run_id, accepted.tenant_id, accepted.thread_id),
    ).fetchall()
    return [
        {"role": str(row["role"]), "content": str(row["content_text"])}
        for row in reversed(rows)
    ]


def _connected_profile(
    database: sqlite3.Connection,
    accepted: AcceptedRunLike,
    requested: str,
) -> tuple[str, str]:
    requested_filter = "AND connection.provider_id = ?" if requested != "auto" else ""
    parameters: list[str] = [accepted.tenant_id]
    if requested_filter:
        parameters.append(requested)
    rows = database.execute(
        f"""
        SELECT connection.provider_id, connection.tenant_id,
               CASE WHEN connection.tenant_id = ? THEN 0 ELSE 1 END AS scope_rank
        FROM provider_connections AS connection
        WHERE connection.status = 'connected'
          AND (
              connection.tenant_id = ?
              OR EXISTS (
                  SELECT 1
                  FROM platform_authority_grants AS authority
                  WHERE authority.authority_id = 'platform_owner'
                    AND authority.tenant_id = connection.tenant_id
                    AND authority.active = 1
              )
          )
          {requested_filter}
        ORDER BY scope_rank,
                 connection.updated_at DESC
        LIMIT 1
        """,
        [accepted.tenant_id, *parameters],
    ).fetchall()
    if not rows:
        raise DirectModelError(
            "provider_not_connected",
            (
                "Эта модель ещё не подключена суперадминистратором."
                if requested != "auto"
                else "Суперадминистратор ещё не подключил ни одного агента."
            ),
        )
    return str(rows[0]["provider_id"]), str(rows[0]["tenant_id"])


def _validated_weather_tool_call(arguments: object) -> ModelToolCall:
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            arguments = None
    if not isinstance(arguments, dict):
        raise DirectModelError(
            "model_tool_call_invalid",
            "Модель передала погодному сервису неизвестные параметры.",
        )
    location = arguments.get("location")
    forecast_days = arguments.get("forecastDays")
    if (
        not isinstance(location, str)
        or not location.strip()
        or len(location.strip()) > 160
        or isinstance(forecast_days, bool)
        or not isinstance(forecast_days, int)
        or not 1 <= forecast_days <= 7
    ):
        raise DirectModelError(
            "model_tool_call_invalid",
            "Модель не указала корректный город и период прогноза.",
        )
    return ModelToolCall(
        name="get_weather",
        arguments={
            "location": location.strip(),
            "forecastDays": forecast_days,
        },
    )


def _turn_from_decision(text: str) -> ModelTurn:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        raise DirectModelError(
            "model_response_invalid",
            "Модель вернула ответ неизвестного формата.",
        ) from None
    if not isinstance(value, dict):
        raise DirectModelError(
            "model_response_invalid",
            "Модель вернула ответ неизвестного формата.",
        )
    if value.get("type") == "tool" and value.get("toolName") == "get_weather":
        return ModelTurn(
            tool_call=_validated_weather_tool_call(
                {
                    "location": value.get("location"),
                    "forecastDays": value.get("forecastDays"),
                }
            )
        )
    answer = value.get("text")
    if (
        value.get("type") != "answer"
        or not isinstance(answer, str)
        or not answer.strip()
    ):
        raise DirectModelError(
            "model_response_invalid",
            "Модель не сформировала ответ.",
        )
    return ModelTurn(text=answer.strip()[:200_000])


def _mimo_response(
    settings: Settings,
    *,
    tenant_id: str,
    messages: list[dict[str, str]],
    runtime: MimoClientRuntime,
    on_delta: Callable[[str], None],
    cancellation_signal: threading.Event | None = None,
) -> ModelTurn:
    try:
        api_key = load_mimo_key(settings, tenant_id=tenant_id)
    except LocalProviderAuthorityError as exc:
        raise DirectModelError(exc.code, exc.message) from None
    base_url = (
        os.getenv(
            "KOLIBRI_V3_MIMO_BASE_URL",
            "https://token-plan-sgp.xiaomimimo.com/v1",
        )
        .strip()
        .rstrip("/")
    )
    parsed = urlsplit(base_url)
    if parsed.scheme != "https" or parsed.path != "/v1":
        raise DirectModelError(
            "mimo_base_url_invalid", "Адрес MiMo API настроен неверно."
        )
    chat_model = os.getenv(
        "KOLIBRI_V3_MIMO_CHAT_MODEL",
        os.getenv("KOLIBRI_V3_MIMO_MODEL", "mimo-v2.5"),
    ).strip()
    try:
        request_payload: dict[str, Any] = {
            "model": chat_model,
            "messages": messages,
            "stream": True,
            "thinking": {"type": "disabled"},
        }
        response = runtime.stream(
            f"{base_url}/chat/completions",
            api_key=api_key,
            payload=request_payload,
        )
        if response.status_code in {400, 422}:
            response.close()
            request_payload = {
                "model": chat_model,
                "messages": messages,
                "stream": True,
                "thinking": {"type": "disabled"},
            }
            response = runtime.stream(
                f"{base_url}/chat/completions",
                api_key=api_key,
                payload=request_payload,
            )
    except httpx.HTTPError:
        raise DirectModelError(
            "mimo_request_failed",
            "MiMo Code сейчас недоступен. Повторите запрос.",
        ) from None
    if response.status_code in {401, 403}:
        response.close()
        raise DirectModelError(
            "mimo_api_key_rejected",
            "MiMo отклонил ключ. Подключите его повторно в личном кабинете.",
        )
    if response.status_code != 200:
        status_code = response.status_code
        response.close()
        raise DirectModelError(
            "mimo_request_failed",
            f"MiMo Code вернул HTTP {status_code}.",
        )

    text_parts: list[str] = []
    tool_name = ""
    tool_argument_parts: list[str] = []
    try:
        for line in response.iter_lines():
            if (
                cancellation_signal is not None
                and cancellation_signal.is_set()
            ):
                raise DirectModelError(
                    "run_cancelled",
                    "Задача остановлена пользователем.",
                )
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if not data or data == "[DONE]":
                continue
            try:
                payload: Any = json.loads(data)
                delta = payload["choices"][0]["delta"]
            except (ValueError, KeyError, IndexError, TypeError):
                continue
            if not isinstance(delta, dict):
                continue
            content = delta.get("content")
            if isinstance(content, str) and content:
                text_parts.append(content)
                on_delta(content)
            calls = delta.get("tool_calls")
            if not isinstance(calls, list):
                continue
            for call in calls:
                function = call.get("function") if isinstance(call, dict) else None
                if not isinstance(function, dict):
                    continue
                name = function.get("name")
                arguments = function.get("arguments")
                if isinstance(name, str) and name:
                    tool_name = name
                if isinstance(arguments, str) and arguments:
                    tool_argument_parts.append(arguments)
    except (httpx.HTTPError, UnicodeError):
        raise DirectModelError(
            "mimo_request_failed",
            "Поток MiMo Code был прерван. Повторите запрос.",
        ) from None
    finally:
        response.close()

    if tool_name:
        if text_parts:
            raise DirectModelError(
                "mimo_mixed_response",
                "MiMo Code смешал текст и вызов инструмента.",
            )
        if tool_name != "get_weather":
            raise DirectModelError(
                "model_tool_not_supported",
                "Модель выбрала неподдерживаемый инструмент.",
            )
        return ModelTurn(
            tool_call=_validated_weather_tool_call("".join(tool_argument_parts))
        )

    text = "".join(text_parts)
    if not text.strip():
        raise DirectModelError("mimo_response_empty", "MiMo Code вернул пустой ответ.")
    return ModelTurn(text=text.strip()[:200_000])


def _mimo_estimate_response(
    settings: Settings,
    *,
    tenant_id: str,
    messages: list[dict[str, str]],
    runtime: MimoClientRuntime,
) -> GeneratedEstimateProposal:
    try:
        api_key = load_mimo_key(settings, tenant_id=tenant_id)
    except LocalProviderAuthorityError as exc:
        raise DirectModelError(exc.code, exc.message) from None
    base_url = (
        os.getenv(
            "KOLIBRI_V3_MIMO_BASE_URL",
            "https://token-plan-sgp.xiaomimimo.com/v1",
        )
        .strip()
        .rstrip("/")
    )
    parsed = urlsplit(base_url)
    if parsed.scheme != "https" or parsed.path != "/v1":
        raise DirectModelError(
            "mimo_base_url_invalid",
            "Адрес MiMo API настроен неверно.",
        )
    today = datetime.now(timezone.utc).date().isoformat()
    instructions = estimate_proposal_instructions(today=today)
    estimate_model = os.getenv(
        "KOLIBRI_V3_MIMO_ESTIMATE_MODEL",
        os.getenv("KOLIBRI_V3_MIMO_MODEL", "mimo-v2.5-pro"),
    ).strip()
    try:
        response = runtime.post(
            f"{base_url}/chat/completions",
            api_key=api_key,
            payload={
                "model": estimate_model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            instructions
                            + "\nJSON Schema:\n"
                            + json.dumps(
                                ESTIMATE_PROPOSAL_SCHEMA,
                                ensure_ascii=False,
                                sort_keys=True,
                                separators=(",", ":"),
                            )
                        ),
                    },
                    *messages,
                ],
                "stream": False,
                "response_format": {"type": "json_object"},
            },
        )
    except httpx.HTTPError:
        raise DirectModelError(
            "mimo_request_failed",
            "MiMo Code сейчас недоступен. Повторите запрос.",
        ) from None
    if response.status_code in {401, 403}:
        raise DirectModelError(
            "mimo_api_key_rejected",
            "MiMo отклонил ключ. Подключите его повторно в личном кабинете.",
        )
    if response.status_code != 200:
        raise DirectModelError(
            "mimo_request_failed",
            f"MiMo Code вернул HTTP {response.status_code}.",
        )
    try:
        payload: Any = response.json()
        text = payload["choices"][0]["message"]["content"]
        if not isinstance(text, str) or not text.strip():
            raise TypeError
        return parse_generated_estimate(text)
    except (ValueError, KeyError, IndexError, TypeError, ValidationError):
        raise DirectModelError(
            "estimate_proposal_invalid",
            "MiMo Code не сформировал корректные строки сметы.",
        ) from None


def _mimo_plastering_intake(
    settings: Settings,
    *,
    tenant_id: str,
    messages: list[dict[str, str]],
    runtime: MimoClientRuntime,
    runtime_guidance: str,
) -> PlasteringIntake:
    try:
        api_key = load_mimo_key(settings, tenant_id=tenant_id)
    except LocalProviderAuthorityError as exc:
        raise DirectModelError(exc.code, exc.message) from None
    base_url = (
        os.getenv(
            "KOLIBRI_V3_MIMO_BASE_URL",
            "https://token-plan-sgp.xiaomimimo.com/v1",
        )
        .strip()
        .rstrip("/")
    )
    parsed = urlsplit(base_url)
    if parsed.scheme != "https" or parsed.path != "/v1":
        raise DirectModelError(
            "mimo_base_url_invalid",
            "Адрес MiMo API настроен неверно.",
        )
    model = os.getenv(
        "KOLIBRI_V3_MIMO_ESTIMATE_MODEL",
        os.getenv("KOLIBRI_V3_MIMO_MODEL", "mimo-v2.5-pro"),
    ).strip()
    instructions = plastering_intake_instructions(
        today=datetime.now(timezone.utc).date().isoformat(),
        runtime_guidance=runtime_guidance,
    )
    try:
        response = runtime.post(
            f"{base_url}/chat/completions",
            api_key=api_key,
            payload={
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            instructions
                            + "\nJSON Schema:\n"
                            + json.dumps(
                                PLASTERING_INTAKE_SCHEMA,
                                ensure_ascii=False,
                                sort_keys=True,
                                separators=(",", ":"),
                            )
                        ),
                    },
                    *messages,
                ],
                "stream": False,
                "response_format": {"type": "json_object"},
            },
        )
    except httpx.HTTPError:
        raise DirectModelError(
            "mimo_request_failed",
            "MiMo Code сейчас недоступен. Повторите запрос.",
        ) from None
    if response.status_code in {401, 403}:
        raise DirectModelError(
            "mimo_api_key_rejected",
            "MiMo отклонил ключ. Подключите его повторно в личном кабинете.",
        )
    if response.status_code != 200:
        raise DirectModelError(
            "mimo_request_failed",
            f"MiMo Code вернул HTTP {response.status_code}.",
        )
    try:
        value: Any = response.json()
        text = value["choices"][0]["message"]["content"]
        if not isinstance(text, str) or not text.strip():
            raise TypeError
        return parse_plastering_intake(text)
    except (ValueError, KeyError, IndexError, TypeError):
        raise DirectModelError(
            "estimate_intake_invalid",
            "MiMo Code не нормализовал исходные данные сметы.",
        ) from None


def _codex_plastering_intake(
    settings: Settings,
    *,
    messages: list[dict[str, str]],
    runtime: CodexAppServerRuntime,
    tenant_id: str,
    product_thread_id: str,
    runtime_guidance: str,
    model: str | None,
    effort: str | None,
    service_tier: str | None,
) -> PlasteringIntake:
    conversation = "\n\n".join(
        f"{'Пользователь' if item['role'] == 'user' else 'Kolibri'}:\n{item['content']}"
        for item in messages
    )
    initial_prompt = (
        "Ниже канонический снимок разговора Kolibri. "
        "Нормализуй исходные данные для Estimate Engine.\n\n"
        f"{conversation}"
    )
    try:
        text = runtime.complete(
            tenant_id=tenant_id,
            product_thread_id=product_thread_id,
            initial_prompt=initial_prompt,
            followup_prompt=messages[-1]["content"],
            output_schema=PLASTERING_INTAKE_SCHEMA,
            instructions=plastering_intake_instructions(
                today=datetime.now(timezone.utc).date().isoformat(),
                runtime_guidance=runtime_guidance,
            ),
            timeout=settings.direct_model_timeout_seconds,
            execution_profile="estimate-intake",
            model=model,
            effort=effort,
            service_tier=service_tier,
        )
        return parse_plastering_intake(text)
    except CodexAppServerAuthenticationError:
        raise DirectModelError(
            "codex_login_required",
            "Сначала выполните вход в Codex CLI на этом компьютере.",
        ) from None
    except CodexAppServerError as exc:
        logger.warning("Codex estimate intake failed: %s", exc)
        raise DirectModelError(
            "codex_request_failed",
            "Codex app-server сейчас недоступен. Повторите запрос.",
        ) from None
    except ValueError:
        raise DirectModelError(
            "estimate_intake_invalid",
            "Codex не нормализовал исходные данные сметы.",
        ) from None


def _codex_estimate_response(
    settings: Settings,
    *,
    messages: list[dict[str, str]],
    runtime: CodexAppServerRuntime,
    tenant_id: str,
    product_thread_id: str,
) -> GeneratedEstimateProposal:
    conversation = "\n\n".join(
        f"{'Пользователь' if item['role'] == 'user' else 'Kolibri'}:\n{item['content']}"
        for item in messages
    )
    initial_prompt = (
        "Ниже канонический снимок разговора Kolibri. "
        "Сформируй предварительную смету по последнему запросу.\n\n"
        f"{conversation}"
    )
    try:
        text = runtime.complete(
            tenant_id=tenant_id,
            product_thread_id=product_thread_id,
            initial_prompt=initial_prompt,
            followup_prompt=messages[-1]["content"],
            output_schema=ESTIMATE_PROPOSAL_SCHEMA,
            instructions=estimate_proposal_instructions(
                today=datetime.now(timezone.utc).date().isoformat(),
            ),
            timeout=settings.direct_model_timeout_seconds,
            execution_profile="estimate",
            model=(os.getenv("KOLIBRI_V3_CODEX_ESTIMATE_MODEL", "").strip() or None),
            effort=os.getenv(
                "KOLIBRI_V3_CODEX_ESTIMATE_EFFORT",
                "low",
            ).strip(),
        )
        return parse_generated_estimate(text)
    except CodexAppServerAuthenticationError:
        raise DirectModelError(
            "codex_login_required",
            "Сначала выполните вход в Codex CLI на этом компьютере.",
        ) from None
    except CodexAppServerError as exc:
        logger.warning("Codex estimate request failed: %s", exc)
        raise DirectModelError(
            "codex_request_failed",
            "Codex app-server сейчас недоступен. Повторите запрос.",
        ) from None
    except (ValueError, ValidationError):
        raise DirectModelError(
            "estimate_proposal_invalid",
            "Codex не сформировал корректные строки сметы.",
        ) from None


def _codex_response(
    settings: Settings,
    *,
    messages: list[dict[str, str]],
    runtime: CodexAppServerRuntime,
    tenant_id: str,
    product_thread_id: str,
    on_delta: Callable[[str], None],
    model: str | None = None,
    effort: str | None = None,
    service_tier: str | None = None,
) -> ModelTurn:
    conversation = "\n\n".join(
        f"{'Пользователь' if item['role'] == 'user' else 'Kolibri'}:\n{item['content']}"
        for item in messages
    )
    initial_prompt = (
        "Ниже канонический снимок разговора Kolibri. "
        "Ответь на последний запрос пользователя.\n\n"
        f"{conversation}"
    )
    followup_prompt = messages[-1]["content"]
    try:
        text = runtime.complete(
            tenant_id=tenant_id,
            product_thread_id=product_thread_id,
            initial_prompt=initial_prompt,
            followup_prompt=followup_prompt,
            output_schema=None,
            instructions=AGENT_CHAT_INSTRUCTIONS,
            timeout=settings.direct_model_timeout_seconds,
            on_delta=on_delta,
            execution_profile="chat",
            model=(
                model
                if model is not None
                else os.getenv(
                    "KOLIBRI_V3_CODEX_CHAT_MODEL",
                    "gpt-5.5",
                ).strip()
            ),
            effort=(
                effort
                if effort is not None
                else os.getenv(
                    "KOLIBRI_V3_CODEX_CHAT_EFFORT",
                    "low",
                ).strip()
            ),
            service_tier=service_tier,
        )
    except CodexAppServerAuthenticationError:
        raise DirectModelError(
            "codex_login_required",
            "Сначала выполните вход в Codex CLI на этом компьютере.",
        ) from None
    except CodexAppServerError as exc:
        logger.warning("Codex app-server request failed: %s", exc)
        raise DirectModelError(
            "codex_request_failed",
            "Codex app-server сейчас недоступен. Повторите запрос.",
        ) from None
    return ModelTurn(text=text.strip()[:200_000])


def _validated_frozen_codex_selection(
    settings: Settings,
    *,
    runtime: CodexAppServerRuntime,
    model: str | None,
    effort: str | None,
    service_tier: str | None,
    selection_required: bool,
) -> tuple[str | None, str | None, str | None]:
    """Validate an accepted run's immutable Codex selection before execution.

    The automatic profile has no user-frozen pair and retains the server-owned
    chat defaults. An explicit Codex profile requires a complete pair. A
    partially populated or now-unknown selection is an explicit run failure:
    execution must never silently switch an accepted concrete selection.
    """

    if model is None and effort is None:
        if selection_required:
            raise DirectModelError(
                "codex_model_selection_missing",
                "Для запуска Codex не сохранена модель. Выберите модель заново.",
            )
        if service_tier is not None:
            raise DirectModelError(
                "codex_model_selection_invalid",
                "Сохранённая скорость не связана с моделью. Выберите модель заново.",
            )
        return None, None, None
    if model is None or effort is None:
        raise DirectModelError(
            "codex_model_selection_invalid",
            "Сохранённые настройки модели неполны. Выберите модель заново.",
        )
    try:
        catalog = runtime.list_models(
            timeout=min(settings.direct_model_timeout_seconds, 10.0),
        )
    except CodexAppServerAuthenticationError:
        raise DirectModelError(
            "codex_login_required",
            "Сначала выполните вход в Codex CLI на этом компьютере.",
        ) from None
    except CodexAppServerError as exc:
        logger.warning("Codex model catalog validation failed: %s", exc)
        raise DirectModelError(
            "codex_model_catalog_unavailable",
            "Каталог моделей Codex сейчас недоступен. Повторите запрос.",
        ) from None

    selected = next((item for item in catalog if item.id == model), None)
    if selected is None:
        raise DirectModelError(
            "codex_model_not_supported",
            "Сохранённая модель Codex больше недоступна. Выберите другую модель.",
        )
    supported_efforts = {
        effort_id for effort_id, _description in selected.supported_reasoning_efforts
    }
    if effort not in supported_efforts:
        raise DirectModelError(
            "codex_reasoning_effort_not_supported",
            (
                "Сохранённый уровень рассуждений недоступен для этой модели. "
                "Выберите его заново."
            ),
        )
    supported_tiers = {
        tier_id for tier_id, _name, _description in selected.service_tiers
    }
    if service_tier is not None and service_tier not in supported_tiers:
        raise DirectModelError(
            "codex_service_tier_not_supported",
            ("Сохранённая скорость недоступна для этой модели. Выберите её заново."),
        )
    return selected.id, effort, service_tier


def _validated_developer_access_context(
    *,
    access_mode: str | None,
    sandbox: str | None,
    approval_policy: str | None,
    approvals_reviewer: str | None,
) -> tuple[str, str, str | None]:
    expected = {
        "auto": ("workspace-write", "on-request", "auto_review"),
        "full": ("danger-full-access", "never", None),
    }
    selected = expected.get(access_mode or "")
    actual = (sandbox, approval_policy, approvals_reviewer)
    if selected is None or actual != selected:
        raise DirectModelError(
            "developer_access_context_invalid",
            "Контекст доступа агента недействителен. Создайте новый запуск.",
        )
    return selected


def _developer_activity_callback(
    settings: Settings,
    *,
    accepted: AcceptedRunLike,
    workspace_root: Path,
) -> Callable[[str, dict[str, Any]], None]:
    activity_tools: dict[str, str] = {}

    def persist_activity(phase: str, item: dict[str, Any]) -> None:
        item_id = _redact_developer_text(item.get("id"), limit=160)
        tool_name, arguments, result = _developer_activity_payload(
            item,
            phase=phase,
            workspace_root=workspace_root,
        )
        if phase == "started":
            activity_tools[item_id] = _start_tool_stage(
                settings,
                accepted,
                tool_name=tool_name,
                arguments=arguments,
            )
            return
        tool_call_id = activity_tools.pop(item_id, None)
        if tool_call_id is None:
            tool_call_id = _start_tool_stage(
                settings,
                accepted,
                tool_name=tool_name,
                arguments=arguments,
            )
        _finish_tool_stage(
            settings,
            accepted,
            tool_call_id=tool_call_id,
            result=result,
        )

    return persist_activity


def _codex_developer_response(
    settings: Settings,
    *,
    accepted: AcceptedRunLike,
    messages: list[dict[str, str]],
    runtime: CodexAppServerRuntime,
    on_delta: Callable[[str], None],
    sandbox: str,
    approval_policy: str,
    approvals_reviewer: str | None,
    model: str | None,
    effort: str | None,
    service_tier: str | None,
) -> ModelTurn:
    workspace_root = settings.developer_workspace_root
    if not settings.developer_agent_enabled or workspace_root is None:
        raise DirectModelError(
            "developer_agent_unavailable",
            "Агент-разработчик не настроен на этом runtime.",
        )

    conversation = "\n\n".join(
        f"{'Пользователь' if item['role'] == 'user' else 'Kolibri'}:\n{item['content']}"
        for item in messages
    )
    initial_prompt = (
        "Ниже канонический снимок разговора с владельцем KolibriAI. "
        "Выполни последний запрос как задачу разработки внутри текущего "
        "репозитория.\n\n"
        f"{conversation}"
    )
    persist_activity = _developer_activity_callback(
        settings,
        accepted=accepted,
        workspace_root=workspace_root,
    )

    try:
        text = runtime.complete(
            tenant_id=accepted.tenant_id,
            product_thread_id=accepted.thread_id,
            initial_prompt=initial_prompt,
            followup_prompt=messages[-1]["content"],
            output_schema=None,
            instructions=AGENT_DEVELOPER_INSTRUCTIONS,
            timeout=settings.developer_agent_timeout_seconds,
            on_delta=on_delta,
            on_activity=persist_activity,
            execution_profile="developer",
            model=(
                model
                if model is not None
                else (
                    os.getenv(
                        "KOLIBRI_V3_CODEX_DEVELOPER_MODEL",
                        "",
                    ).strip()
                    or None
                )
            ),
            effort=(
                effort
                if effort is not None
                else os.getenv(
                    "KOLIBRI_V3_CODEX_DEVELOPER_EFFORT",
                    "medium",
                ).strip()
            ),
            service_tier=service_tier,
            workspace_root=workspace_root,
            sandbox=sandbox,
            approval_policy=approval_policy,
            approvals_reviewer=approvals_reviewer,
        )
    except CodexAppServerAuthenticationError:
        raise DirectModelError(
            "codex_login_required",
            "Сначала выполните вход в Codex CLI на этом компьютере.",
        ) from None
    except CodexAppServerError as exc:
        logger.warning("Codex developer request failed: %s", exc)
        raise DirectModelError(
            "developer_agent_failed",
            "Агент-разработчик не завершил задачу. Повторите запрос.",
        ) from None
    return ModelTurn(text=text.strip()[:200_000])


def _mimo_developer_response(
    settings: Settings,
    *,
    accepted: AcceptedRunLike,
    messages: list[dict[str, str]],
    runtime: MimoDeveloperServerRuntime,
    on_delta: Callable[[str], None],
    access_mode: str,
) -> ModelTurn:
    workspace_root = settings.developer_workspace_root
    if not settings.developer_agent_enabled or workspace_root is None:
        raise DirectModelError(
            "developer_agent_unavailable",
            "Агент-разработчик не настроен на этом runtime.",
        )
    conversation = "\n\n".join(
        f"{'Пользователь' if item['role'] == 'user' else 'Kolibri'}:\n{item['content']}"
        for item in messages
    )
    prompt = (
        "Ниже канонический снимок разговора с владельцем KolibriAI. "
        "Выполни последний запрос как задачу разработки внутри текущего "
        "репозитория. Не раскрывай секреты и не выполняй git push или deploy "
        "без отдельного явного запроса владельца.\n\n"
        f"{conversation}"
    )
    persist_activity = _developer_activity_callback(
        settings,
        accepted=accepted,
        workspace_root=workspace_root,
    )
    try:
        result = runtime.complete(
            workspace_root=workspace_root,
            prompt=prompt,
            run_id=accepted.run_id,
            conversation_key=(f"{accepted.tenant_id}:{accepted.thread_id}"),
            timeout=settings.developer_agent_timeout_seconds,
            access_mode=access_mode,
            on_delta=on_delta,
            on_activity=persist_activity,
        )
    except MimoDeveloperRuntimeError as exc:
        raise DirectModelError(exc.code, exc.message) from None
    return ModelTurn(text=result.text.strip()[:200_000])


def _finish_success(
    settings: Settings,
    accepted: AcceptedRunLike,
    text: str,
    *,
    widget: ProductWidget | None = None,
    text_stream: _TextRunStream | None = None,
    generated_image: PreparedGeneratedImageArtifact | None = None,
) -> None:
    if widget is not None and generated_image is not None:
        raise ValueError("generated image and widget are mutually exclusive")
    database = connect_database(settings.database_url)
    now = utc_now()
    try:
        with transaction(database, immediate=True):
            run = database.execute(
                """
                SELECT project_id, thread_id, client_run_id,
                       requested_by_user_id, last_event_sequence, status,
                       run.selected_profile,
                       COALESCE(context.execution_mode, 'standard')
                           AS execution_mode,
                       context.platform_authority_epoch,
                       context.access_mode,
                       context.sandbox_profile,
                       context.approval_policy,
                       context.approvals_reviewer,
                       context.trusted_agent_profile_id,
                       context.trusted_agent_profile_epoch,
                       context.trusted_agent_workspace_binding_id,
                       context.trusted_agent_workspace_binding_epoch
                FROM chat_runs AS run
                LEFT JOIN chat_run_execution_contexts AS context
                  ON context.tenant_id = run.tenant_id
                 AND context.run_id = run.id
                WHERE run.tenant_id = ? AND run.id = ?
                """,
                (accepted.tenant_id, accepted.run_id),
            ).fetchone()
            if run is None or str(run["status"]) != "running":
                return
            direct_claim = (
                accepted
                if isinstance(accepted, DirectRunClaim)
                else None
            )
            if direct_claim is not None:
                DirectRunStore.require_owned_in_transaction(
                    database,
                    direct_claim,
                    now_text=now,
                )
            from .platform_admin import (
                PlatformPolicyError,
                enforce_background_execution_policy,
            )

            try:
                enforce_background_execution_policy(
                    database,
                    tenant_id=accepted.tenant_id,
                    user_id=str(run["requested_by_user_id"]),
                    require_developer_access=(
                        str(run["execution_mode"]) == "developer"
                    ),
                )
            except PlatformPolicyError as exc:
                raise DirectModelError(exc.code, exc.message) from exc
            if str(run["execution_mode"]) == "developer":
                from .platform_authority import (
                    PlatformDeveloperAuthorityError,
                    require_persisted_platform_developer_authority,
                )

                frozen_epoch = run["platform_authority_epoch"]
                if frozen_epoch is None:
                    raise DirectModelError(
                        "owner_required",
                        "Owner access is required for developer agent mode.",
                    )
                try:
                    require_persisted_platform_developer_authority(
                        database,
                        tenant_id=accepted.tenant_id,
                        user_id=str(run["requested_by_user_id"]),
                        expected_epoch=int(frozen_epoch),
                    )
                except PlatformDeveloperAuthorityError as exc:
                    raise DirectModelError(exc.code, exc.message) from exc
                _validate_direct_trusted_agent_binding(
                    database,
                    run,
                    tenant_id=accepted.tenant_id,
                )
            if generated_image is not None:
                try:
                    widget = persist_generated_image_artifact(
                        database,
                        accepted,
                        prepared=generated_image,
                        created_at=now,
                    )
                except GeneratedImageArtifactError as exc:
                    raise DirectModelError(exc.code, exc.message) from exc
                text = widget.fallback_text
            sequence_row = database.execute(
                """
                SELECT COALESCE(MAX(sequence), 0) AS value
                FROM chat_messages
                WHERE tenant_id = ? AND thread_id = ?
                """,
                (accepted.tenant_id, accepted.thread_id),
            ).fetchone()
            streamed_text = (
                text_stream.text
                if text_stream is not None and text_stream.started
                else None
            )
            if streamed_text is not None:
                text = streamed_text
            message_id = (
                text_stream.message_id if text_stream is not None else new_id("message")
            )
            tool_call_id = new_id("tool") if widget is not None else None
            tool_arguments = (
                json.dumps(
                    widget.arguments,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                )
                if widget is not None
                else None
            )
            tool_result = (
                widget.tool_result
                if widget is not None and widget.tool_result is not None
                else {
                    "rendered": True,
                    "schemaVersion": "1.0",
                }
                if widget is not None
                else None
            )
            content_json = (
                json.dumps(
                    {
                        "type": "tool-call",
                        "toolCallId": tool_call_id,
                        "toolName": widget.tool_name,
                        "args": widget.arguments,
                        "argsText": tool_arguments,
                        "result": tool_result,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                )
                if widget is not None
                else None
            )
            database.execute(
                """
                INSERT INTO chat_messages (
                    tenant_id, id, project_id, thread_id, sequence,
                    client_message_id, run_id, role, content_text, content_json,
                    created_by_user_id, created_at
                ) VALUES (?, ?, ?, ?, ?, NULL, ?, 'assistant', ?, ?, NULL, ?)
                """,
                (
                    accepted.tenant_id,
                    message_id,
                    accepted.project_id,
                    accepted.thread_id,
                    int(sequence_row["value"]) + 1,
                    accepted.run_id,
                    text,
                    content_json,
                    now,
                ),
            )
            first = int(run["last_event_sequence"]) + 1
            if widget is None and text_stream is not None and text_stream.started:
                events = (
                    {"type": "TEXT_MESSAGE_END", "messageId": message_id},
                    {
                        "type": "RUN_FINISHED",
                        "threadId": accepted.public_thread_id,
                        "runId": accepted.public_run_id,
                        "outcome": {"type": "success"},
                    },
                )
            elif widget is None:
                events = (
                    {
                        "type": "TEXT_MESSAGE_START",
                        "messageId": message_id,
                        "role": "assistant",
                    },
                    {
                        "type": "TEXT_MESSAGE_CONTENT",
                        "messageId": message_id,
                        "delta": text,
                    },
                    {"type": "TEXT_MESSAGE_END", "messageId": message_id},
                    {
                        "type": "RUN_FINISHED",
                        "threadId": accepted.public_thread_id,
                        "runId": accepted.public_run_id,
                        "outcome": {"type": "success"},
                    },
                )
            else:
                events = (
                    {
                        "type": "TOOL_CALL_START",
                        "toolCallId": tool_call_id,
                        "toolCallName": widget.tool_name,
                        "parentMessageId": message_id,
                    },
                    {
                        "type": "TOOL_CALL_ARGS",
                        "toolCallId": tool_call_id,
                        "delta": tool_arguments,
                    },
                    {
                        "type": "TOOL_CALL_END",
                        "toolCallId": tool_call_id,
                    },
                    {
                        "type": "TOOL_CALL_RESULT",
                        "messageId": new_id("message"),
                        "toolCallId": tool_call_id,
                        "content": json.dumps(
                            tool_result,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                        "role": "tool",
                    },
                    {
                        "type": "RUN_FINISHED",
                        "threadId": accepted.public_thread_id,
                        "runId": accepted.public_run_id,
                        "outcome": {"type": "success"},
                    },
                )
            for offset, event in enumerate(events):
                _insert_event(
                    database,
                    tenant_id=accepted.tenant_id,
                    run_id=accepted.run_id,
                    sequence=first + offset,
                    event=event,
                    created_at=now,
                )
            database.execute(
                """
                UPDATE chat_runs
                SET assistant_message_id = ?, status = 'succeeded',
                    outcome = 'success', last_event_sequence = ?,
                    error_code = NULL, heartbeat_at = ?, updated_at = ?, finished_at = ?
                WHERE tenant_id = ? AND id = ?
                """,
                (
                    message_id,
                    first + len(events) - 1,
                    now,
                    now,
                    now,
                    accepted.tenant_id,
                    accepted.run_id,
                ),
            )
            database.execute(
                """
                UPDATE chat_threads
                SET message_count = message_count + 1,
                    last_message_at = ?, updated_at = ?
                WHERE tenant_id = ? AND id = ?
                """,
                (now, now, accepted.tenant_id, accepted.thread_id),
            )
            if direct_claim is not None:
                DirectRunStore.complete_in_transaction(
                    database,
                    direct_claim,
                    now_text=now,
                )
            logger.info(
                "Direct model completed run=%s total_ms=%d streamed=%s",
                accepted.public_run_id,
                (round(text_stream.elapsed_ms()) if text_stream is not None else -1),
                bool(text_stream is not None and text_stream.started),
            )
    finally:
        database.close()


def _finish_error(
    settings: Settings,
    accepted: AcceptedRunLike,
    error: DirectModelError,
) -> None:
    database = connect_database(settings.database_url)
    now = utc_now()
    try:
        with transaction(database, immediate=True):
            run = database.execute(
                """
                SELECT last_event_sequence, status
                FROM chat_runs WHERE tenant_id = ? AND id = ?
                """,
                (accepted.tenant_id, accepted.run_id),
            ).fetchone()
            if run is None or str(run["status"]) != "running":
                return
            direct_claim = (
                accepted
                if isinstance(accepted, DirectRunClaim)
                else None
            )
            if direct_claim is not None:
                DirectRunStore.require_owned_in_transaction(
                    database,
                    direct_claim,
                    now_text=now,
                )
            sequence = int(run["last_event_sequence"]) + 1
            _insert_event(
                database,
                tenant_id=accepted.tenant_id,
                run_id=accepted.run_id,
                sequence=sequence,
                event={
                    "type": "RUN_ERROR",
                    "code": error.code[:96],
                    "message": error.message[:500],
                },
                created_at=now,
            )
            database.execute(
                """
                UPDATE chat_runs
                SET status = 'failed', outcome = 'failure',
                    last_event_sequence = ?, error_code = ?,
                    heartbeat_at = ?, updated_at = ?, finished_at = ?
                WHERE tenant_id = ? AND id = ?
                """,
                (
                    sequence,
                    error.code[:96],
                    now,
                    now,
                    now,
                    accepted.tenant_id,
                    accepted.run_id,
                ),
            )
            if direct_claim is not None:
                DirectRunStore.block_in_transaction(
                    database,
                    direct_claim,
                    code=error.code,
                    now_text=now,
                )
    finally:
        database.close()


def _estimate_skill_plan_for_run(
    settings: Settings,
    accepted: AcceptedRunLike,
) -> RuntimeSkillPlan:
    """Load the immutable plan selected when the run was accepted.

    Runs created before runtime-skill evidence existed are upgraded once on
    execution with the current reviewed plan.  New runs record it atomically in
    ``accept_run``.  A mismatched persisted record is a safe failure rather
    than a chance to run a model under changed instructions.
    """

    database = connect_database(settings.database_url)
    try:
        with transaction(database, immediate=True):
            plan = load_runtime_skill_plan(
                database,
                tenant_id=accepted.tenant_id,
                run_id=accepted.run_id,
            )
            if plan is None:
                plan = estimate_runtime_skill_plan()
                persist_runtime_skill_plan(
                    database,
                    tenant_id=accepted.tenant_id,
                    run_id=accepted.run_id,
                    plan=plan,
                    created_at=utc_now(),
                )
            return plan
    except RuntimeSkillError as exc:
        raise DirectModelError(
            "runtime_skill_context_invalid",
            "Не удалось проверить серверный контекст сметного запуска.",
        ) from exc
    finally:
        database.close()


def _runtime_error(
    error: DirectModelError,
    *,
    category: str = "execution",
    retryable: bool = False,
) -> AgentRuntimeError:
    return AgentRuntimeError(
        error.code,
        error.message,
        category=category,  # type: ignore[arg-type]
        retryable=retryable,
    )


def _runtime_messages(
    request: AgentRuntimeRequest,
) -> list[dict[str, str]]:
    return [
        {"role": message.role, "content": message.content}
        for message in request.messages
    ]


def _call_optional(target: object, name: str) -> None:
    callback = getattr(target, name, None)
    if callable(callback):
        callback()


def _codex_runtime_adapter(
    settings: Settings,
    transport: object,
) -> DelegatingAgentRuntime:
    descriptor = AgentRuntimeDescriptor(
        profile_id="codex-cli",
        runtime_id="codex-app-server",
        display_name="Codex",
        auto_priority=20,
        capabilities=AgentRuntimeCapabilities(
            modes=frozenset({"chat", "structured", "developer"}),
            streaming=True,
            structured_output=True,
            activity_events=True,
            persistent_sessions=True,
            model_catalog=True,
        ),
    )

    def execute(request: AgentRuntimeRequest) -> AgentRuntimeResult:
        model: str | None
        effort: str | None
        service_tier: str | None
        selection = request.configuration.selection
        try:
            model, effort, service_tier = _validated_frozen_codex_selection(
                settings,
                runtime=transport,  # type: ignore[arg-type]
                model=selection.model_id,
                effort=selection.reasoning_effort,
                service_tier=selection.service_tier,
                selection_required=(
                    selection.explicit_profile
                    and request.execution_profile not in {"estimate-intake"}
                ),
            )
        except DirectModelError as exc:
            raise _runtime_error(exc, category="configuration") from None

        if request.mode == "structured":
            try:
                intake = _codex_plastering_intake(
                    settings,
                    messages=_runtime_messages(request),
                    runtime=transport,  # type: ignore[arg-type]
                    tenant_id=request.tenant_id,
                    product_thread_id=request.thread_id,
                    runtime_guidance=request.guidance or "",
                    model=model,
                    effort=effort,
                    service_tier=service_tier,
                )
            except DirectModelError as exc:
                raise _runtime_error(exc) from None
            return AgentRuntimeResult(
                text=intake.model_dump_json(by_alias=True),
            )

        if model is None:
            if request.execution_profile == "developer":
                model = (
                    os.getenv(
                        "KOLIBRI_V3_CODEX_DEVELOPER_MODEL",
                        "",
                    ).strip()
                    or None
                )
            else:
                model = os.getenv(
                    "KOLIBRI_V3_CODEX_CHAT_MODEL",
                    "gpt-5.5",
                ).strip()
        if effort is None:
            effort = os.getenv(
                (
                    "KOLIBRI_V3_CODEX_DEVELOPER_EFFORT"
                    if request.execution_profile == "developer"
                    else "KOLIBRI_V3_CODEX_CHAT_EFFORT"
                ),
                ("medium" if request.execution_profile == "developer" else "low"),
            ).strip()
        access = request.configuration.access
        workspace = request.configuration.workspace
        try:
            text = transport.complete(  # type: ignore[attr-defined]
                tenant_id=request.tenant_id,
                product_thread_id=request.thread_id,
                initial_prompt=request.initial_prompt,
                followup_prompt=request.followup_prompt,
                output_schema=None,
                instructions=request.instructions,
                timeout=request.timeout_seconds,
                on_delta=request.on_delta,
                on_activity=request.on_activity,
                execution_profile=request.execution_profile,
                model=model,
                effort=effort,
                service_tier=service_tier,
                workspace_root=workspace.root,
                sandbox=access.sandbox,
                approval_policy=access.approval_policy,
                approvals_reviewer=access.approvals_reviewer,
                cancellation_signal=request.cancellation_signal,
            )
        except CodexAppServerAuthenticationError:
            raise AgentRuntimeError(
                "codex_login_required",
                "Сначала выполните вход в Codex CLI на этом компьютере.",
                category="authentication",
            ) from None
        except CodexAppServerError as exc:
            logger.warning("Codex agent runtime failed: %s", exc)
            code = (
                "developer_agent_failed"
                if request.mode == "developer"
                else "codex_request_failed"
            )
            message = (
                "Агент-разработчик не завершил задачу. Повторите запрос."
                if request.mode == "developer"
                else "Codex app-server сейчас недоступен. Повторите запрос."
            )
            raise AgentRuntimeError(
                code,
                message,
                category="unavailable",
                retryable=True,
            ) from None
        normalized = str(text).strip()[:200_000]
        if not normalized:
            raise AgentRuntimeError(
                "agent_runtime_response_empty",
                "Выбранный агент вернул пустой ответ.",
                category="invalid_output",
            )
        return AgentRuntimeResult(text=normalized)

    return DelegatingAgentRuntime(
        descriptor=descriptor,
        execute=execute,
        start=lambda: _call_optional(transport, "start"),
        close=lambda: _call_optional(transport, "stop"),
        model_catalog_backend=transport,
    )


def _mimo_runtime_adapter(
    settings: Settings,
    *,
    client_transport: object | None,
    developer_transport: object | None,
) -> DelegatingAgentRuntime:
    supported_modes: set[str] = set()
    if client_transport is not None:
        supported_modes.update({"chat", "structured"})
    if developer_transport is not None:
        supported_modes.add("developer")
    descriptor = AgentRuntimeDescriptor(
        profile_id="mimo-code",
        runtime_id="mimo-code-runtime",
        display_name="MiMo Code",
        auto_priority=10,
        capabilities=AgentRuntimeCapabilities(
            modes=frozenset(supported_modes),  # type: ignore[arg-type]
            streaming=True,
            structured_output=True,
            activity_events=developer_transport is not None,
            persistent_sessions=developer_transport is not None,
            model_catalog=False,
        ),
    )

    def execute(request: AgentRuntimeRequest) -> AgentRuntimeResult:
        selection = request.configuration.selection
        if any(
            value is not None
            for value in (
                selection.model_id,
                selection.reasoning_effort,
                selection.service_tier,
            )
        ):
            raise AgentRuntimeError(
                "agent_model_selection_not_supported",
                "Выбранный агент не поддерживает эти настройки модели.",
                category="configuration",
            )
        if request.mode == "developer":
            if developer_transport is None:
                raise AgentRuntimeError(
                    "developer_agent_unavailable",
                    "Постоянный runtime выбранного агента сейчас недоступен.",
                    category="unavailable",
                    retryable=True,
                )
            workspace = request.configuration.workspace.root
            if workspace is None:
                raise AgentRuntimeError(
                    "developer_workspace_missing",
                    "Рабочая папка агента не настроена.",
                    category="configuration",
                )
            try:
                result = developer_transport.complete(  # type: ignore[attr-defined]
                    workspace_root=workspace,
                    prompt=request.initial_prompt,
                    run_id=request.run_id,
                    conversation_key=(
                        f"{request.tenant_id}:{request.thread_id}:"
                        f"{descriptor.runtime_id}"
                    ),
                    timeout=request.timeout_seconds,
                    access_mode=request.configuration.access.mode,
                    on_delta=request.on_delta or (lambda _delta: None),
                    on_activity=request.on_activity or (lambda _phase, _item: None),
                    cancellation_signal=request.cancellation_signal,
                )
            except MimoDeveloperRuntimeError as exc:
                raise AgentRuntimeError(
                    exc.code,
                    exc.message,
                    category="execution",
                    retryable=exc.code
                    in {
                        "mimo_developer_timeout",
                        "mimo_developer_server_unavailable",
                    },
                ) from None
            text = str(result.text).strip()[:200_000]
            if not text:
                raise AgentRuntimeError(
                    "agent_runtime_response_empty",
                    "Выбранный агент вернул пустой ответ.",
                    category="invalid_output",
                )
            return AgentRuntimeResult(
                text=text,
                session_id=str(result.session_id),
            )
        if client_transport is None:
            raise AgentRuntimeError(
                "agent_runtime_unavailable",
                "Выбранный агент сейчас недоступен.",
                category="unavailable",
                retryable=True,
            )
        try:
            if request.mode == "structured":
                intake = _mimo_plastering_intake(
                    settings,
                    tenant_id=request.credential_tenant_id,
                    messages=_runtime_messages(request),
                    runtime=client_transport,  # type: ignore[arg-type]
                    runtime_guidance=request.guidance or "",
                )
                return AgentRuntimeResult(
                    text=intake.model_dump_json(by_alias=True),
                )
            turn = _mimo_response(
                settings,
                tenant_id=request.credential_tenant_id,
                messages=_runtime_messages(request),
                runtime=client_transport,  # type: ignore[arg-type]
                on_delta=request.on_delta or (lambda _delta: None),
                cancellation_signal=request.cancellation_signal,
            )
        except DirectModelError as exc:
            raise _runtime_error(exc) from None
        if turn.tool_call is not None:
            return AgentRuntimeResult(
                tool_call=AgentToolCall(
                    name=turn.tool_call.name,
                    arguments=turn.tool_call.arguments,
                )
            )
        return AgentRuntimeResult(text=(turn.text or "").strip()[:200_000])

    def start() -> None:
        if client_transport is not None:
            _call_optional(client_transport, "start")
        if developer_transport is not None:
            _call_optional(developer_transport, "start")

    def close() -> None:
        if developer_transport is not None:
            _call_optional(developer_transport, "close")
        if client_transport is not None:
            _call_optional(client_transport, "close")

    return DelegatingAgentRuntime(
        descriptor=descriptor,
        execute=execute,
        start=start,
        close=close,
    )


def build_agent_runtime_registry(
    settings: Settings,
    *,
    runtime_root: Path,
) -> AgentRuntimeRegistry:
    """Create the process-lifetime registry used by the live V3 backend."""

    registry = AgentRuntimeRegistry()
    codex_transport = CodexAppServerRuntime(
        runtime_root=runtime_root / "codex-direct",
    )
    mimo_client = MimoClientRuntime(
        timeout_seconds=settings.direct_model_timeout_seconds,
    )
    mimo_developer_transport: MimoDeveloperServerRuntime | None = None
    if settings.developer_agent_enabled:
        mimo_developer_transport = MimoDeveloperServerRuntime(
            runtime_root=runtime_root / "mimo-developer",
        )
    registry.register(_codex_runtime_adapter(settings, codex_transport))
    registry.register(
        _mimo_runtime_adapter(
            settings,
            client_transport=mimo_client,
            developer_transport=mimo_developer_transport,
        )
    )
    return registry


def _legacy_runtime_registry(
    settings: Settings,
    *,
    codex_transport: object | None,
    mimo_transport: object | None,
    mimo_developer_transport: object | None,
) -> AgentRuntimeRegistry:
    """Compatibility for focused tests and pre-registry in-process callers."""

    registry = AgentRuntimeRegistry()
    if codex_transport is not None:
        registry.register(_codex_runtime_adapter(settings, codex_transport))
    if mimo_transport is not None or mimo_developer_transport is not None:
        registry.register(
            _mimo_runtime_adapter(
                settings,
                client_transport=mimo_transport,
                developer_transport=mimo_developer_transport,
            )
        )
    return registry


def _agent_runtime_request(
    *,
    accepted: AcceptedRunLike,
    mode: str,
    execution_profile: str,
    messages: list[dict[str, str]],
    credential_tenant_id: str,
    initial_prompt: str,
    instructions: str,
    timeout_seconds: float,
    selection: AgentModelSelection,
    access: AgentAccessPolicy,
    workspace: AgentWorkspace,
    output_schema: dict[str, Any] | None = None,
    guidance: str | None = None,
    on_delta: Callable[[str], None] | None = None,
    on_activity: Callable[[str, dict[str, Any]], None] | None = None,
    cancellation_signal: threading.Event | None = None,
) -> AgentRuntimeRequest:
    return AgentRuntimeRequest(
        tenant_id=accepted.tenant_id,
        thread_id=accepted.thread_id,
        run_id=accepted.run_id,
        credential_tenant_id=credential_tenant_id,
        mode=mode,  # type: ignore[arg-type]
        execution_profile=execution_profile,
        messages=tuple(
            AgentRuntimeMessage(
                role=item["role"],  # type: ignore[arg-type]
                content=item["content"],
            )
            for item in messages
        ),
        initial_prompt=initial_prompt,
        followup_prompt=messages[-1]["content"],
        instructions=instructions,
        timeout_seconds=timeout_seconds,
        guidance=guidance,
        configuration=AgentExecutionConfiguration(
            selection=selection,
            access=access,
            workspace=workspace,
        ),
        output_schema=output_schema,
        on_delta=on_delta,
        on_activity=on_activity,
        cancellation_signal=cancellation_signal,
    )


def execute_direct_run(
    settings: Settings,
    accepted: AcceptedRunLike,
    runtime_registry: AgentRuntimeRegistry,
    *,
    cancellation_signal: threading.Event | None = None,
) -> None:
    runtimes = runtime_registry
    registered_image_provider = runtimes.capability(
        IMAGE_GENERATION_CAPABILITY_ID
    )
    image_provider: ImageGenerationProvider = (
        registered_image_provider
        if isinstance(registered_image_provider, ImageGenerationProvider)
        else UnavailableImageGenerationProvider()
    )
    database = connect_database(settings.database_url)
    try:
        run = database.execute(
            """
            SELECT run.selected_profile, run.status,
                   context.run_id AS context_run_id,
                   run.requested_by_user_id,
                   context.execution_mode AS context_execution_mode,
                   context.platform_authority_epoch,
                   context.access_mode, context.access_policy_version,
                   context.sandbox_profile,
                   context.approval_policy, context.approvals_reviewer,
                   context.model_id, context.reasoning_effort,
                   context.service_tier,
                   context.trusted_agent_profile_id,
                   context.trusted_agent_profile_epoch,
                   context.trusted_agent_workspace_binding_id,
                   context.trusted_agent_workspace_binding_epoch
            FROM chat_runs AS run
            LEFT JOIN chat_run_execution_contexts AS context
              ON context.tenant_id = run.tenant_id
             AND context.run_id = run.id
            WHERE run.tenant_id = ? AND run.id = ?
            """,
            (accepted.tenant_id, accepted.run_id),
        ).fetchone()
        if (
            run is None
            or str(run["status"]) != "running"
            or (
                cancellation_signal is not None
                and cancellation_signal.is_set()
            )
        ):
            return
        messages = _history(database, accepted)
        selected_profile = str(run["selected_profile"])
        execution_context_present = run["context_run_id"] is not None
        frozen_model = str(run["model_id"]) if run["model_id"] is not None else None
        frozen_effort = (
            str(run["reasoning_effort"])
            if run["reasoning_effort"] is not None
            else None
        )
        frozen_service_tier = (
            str(run["service_tier"]) if run["service_tier"] is not None else None
        )
        frozen_execution_mode = (
            str(run["context_execution_mode"])
            if run["context_execution_mode"] is not None
            else None
        )
        frozen_platform_authority_epoch = (
            int(run["platform_authority_epoch"])
            if run["platform_authority_epoch"] is not None
            else None
        )
        frozen_access_mode = (
            str(run["access_mode"]) if run["access_mode"] is not None else None
        )
        frozen_access_policy_version = (
            int(run["access_policy_version"])
            if run["access_policy_version"] is not None
            else None
        )
        frozen_sandbox = (
            str(run["sandbox_profile"]) if run["sandbox_profile"] is not None else None
        )
        frozen_approval_policy = (
            str(run["approval_policy"]) if run["approval_policy"] is not None else None
        )
        frozen_approvals_reviewer = (
            str(run["approvals_reviewer"])
            if run["approvals_reviewer"] is not None
            else None
        )
        from .platform_admin import (
            PlatformPolicyError,
            enforce_background_execution_policy,
        )

        try:
            enforce_background_execution_policy(
                database,
                tenant_id=accepted.tenant_id,
                user_id=str(run["requested_by_user_id"]),
                require_developer_access=(
                    frozen_execution_mode == "developer"
                ),
            )
        except PlatformPolicyError as exc:
            raise DirectModelError(exc.code, exc.message) from exc
        if frozen_execution_mode == "developer":
            from .platform_authority import (
                PlatformDeveloperAuthorityError,
                require_persisted_platform_developer_authority,
            )

            if frozen_platform_authority_epoch is None:
                raise DirectModelError(
                    "owner_required",
                    "Owner access is required for developer agent mode.",
                )
            try:
                require_persisted_platform_developer_authority(
                    database,
                    tenant_id=accepted.tenant_id,
                    user_id=str(run["requested_by_user_id"]),
                    expected_epoch=frozen_platform_authority_epoch,
                )
            except PlatformDeveloperAuthorityError as exc:
                raise DirectModelError(exc.code, exc.message) from exc
    finally:
        database.close()
    if isinstance(accepted, DirectRunClaim):
        DirectRunStore(settings.database_url).fence(accepted)
    estimate_requested = is_estimate_generation_prompt(
        messages[-1]["content"],
    )
    text_stream: _TextRunStream | None = None
    try:
        accepted_execution_mode = getattr(
            accepted,
            "execution_mode",
            "standard",
        )
        if not execution_context_present:
            raise DirectModelError(
                "direct_run_context_missing",
                "Контекст запуска модели не найден. Повторите запрос.",
            )
        if accepted_execution_mode != frozen_execution_mode:
            raise DirectModelError(
                "direct_run_context_mismatch",
                "Контекст запуска изменился. Повторите запрос.",
            )
        if frozen_execution_mode == "developer":
            authority_database = connect_database(settings.database_url)
            try:
                _validate_direct_trusted_agent_binding(
                    authority_database,
                    run,
                    tenant_id=accepted.tenant_id,
                )
            finally:
                authority_database.close()
            if frozen_access_policy_version != 2:
                raise DirectModelError(
                    "developer_access_policy_legacy_locked",
                    (
                        "Этот запуск создан со старой политикой доступа и "
                        "не может быть продолжен. Повторите задачу."
                    ),
                )
            (
                developer_sandbox,
                developer_approval_policy,
                developer_approvals_reviewer,
            ) = _validated_developer_access_context(
                access_mode=frozen_access_mode,
                sandbox=frozen_sandbox,
                approval_policy=frozen_approval_policy,
                approvals_reviewer=frozen_approvals_reviewer,
            )
            credential_tenant_id = accepted.tenant_id
            resolved_profile = selected_profile
            if selected_profile == "auto":
                raise DirectModelError(
                    "developer_profile_required",
                    (
                        "Для режима разработчика нужен явно выбранный "
                        "runtime-профиль."
                    ),
                )
            try:
                runtime = runtimes.require(resolved_profile)
            except AgentRuntimeError as exc:
                raise DirectModelError(exc.code, exc.message) from None
            workspace_root = settings.developer_workspace_root
            if not settings.developer_agent_enabled or workspace_root is None:
                raise DirectModelError(
                    "developer_agent_unavailable",
                    "Агент-разработчик не настроен на этом runtime.",
                )
            text_stream = _TextRunStream(
                settings,
                accepted,
                provider=runtime.descriptor.profile_id,
            )
            conversation = "\n\n".join(
                f"{'Пользователь' if item['role'] == 'user' else 'Kolibri'}:"
                f"\n{item['content']}"
                for item in messages
            )
            request = _agent_runtime_request(
                accepted=accepted,
                mode="developer",
                execution_profile="developer",
                messages=messages,
                credential_tenant_id=credential_tenant_id,
                initial_prompt=(
                    "Ниже канонический снимок разговора с владельцем "
                    "KolibriAI. Выполни последний запрос как задачу "
                    "разработки внутри текущего репозитория.\n\n"
                    f"{conversation}"
                ),
                instructions=AGENT_DEVELOPER_INSTRUCTIONS,
                timeout_seconds=settings.developer_agent_timeout_seconds,
                selection=AgentModelSelection(
                    model_id=frozen_model,
                    reasoning_effort=frozen_effort,
                    service_tier=frozen_service_tier,
                    explicit_profile=True,
                ),
                access=AgentAccessPolicy(
                    mode=frozen_access_mode,  # type: ignore[arg-type]
                    sandbox=developer_sandbox,  # type: ignore[arg-type]
                    approval_policy=developer_approval_policy,  # type: ignore[arg-type]
                    approvals_reviewer=developer_approvals_reviewer,
                ),
                workspace=AgentWorkspace(
                    reference="repository",
                    root=workspace_root.resolve(),
                ),
                on_delta=text_stream.append,
                on_activity=_developer_activity_callback(
                    settings,
                    accepted=accepted,
                    workspace_root=workspace_root,
                ),
                cancellation_signal=cancellation_signal,
            )
            try:
                result = runtime.execute(request)
            except AgentRuntimeError as exc:
                raise DirectModelError(exc.code, exc.message) from None
            _finish_success(
                settings,
                accepted,
                result.text or "",
                text_stream=text_stream,
            )
            return
        image_request = resolve_image_prompt(messages)
        if image_request is not None and image_request.action == "clarify":
            _finish_success(
                settings,
                accepted,
                IMAGE_GENERATION_CLARIFICATION,
            )
            return
        if image_request is not None and image_request.prompt is not None:
            provider_request = ImageGenerationRequest(
                tenant_id=accepted.tenant_id,
                project_id=accepted.project_id,
                thread_id=accepted.thread_id,
                run_id=accepted.run_id,
                prompt=image_request.prompt,
                idempotency_key=f"product-image:{accepted.run_id}",
            )
            try:
                image_result = image_provider.generate(
                    provider_request,
                    cancellation_signal=cancellation_signal,
                )
                if (
                    cancellation_signal is not None
                    and cancellation_signal.is_set()
                ):
                    raise ImageGenerationError(
                        "run_cancelled",
                        "Задача остановлена пользователем.",
                    )
                prepared_image = prepare_generated_image_artifact(
                    settings,
                    accepted,
                    prompt=image_request.prompt,
                    provider=image_provider,
                    result=image_result,
                )
            except ImageGenerationError as exc:
                raise DirectModelError(exc.code, exc.message) from exc
            except GeneratedImageArtifactError as exc:
                raise DirectModelError(exc.code, exc.message) from exc
            except Exception:
                logger.exception(
                    "Image provider failed run=%s",
                    accepted.public_run_id,
                )
                raise DirectModelError(
                    "image_generation_failed",
                    (
                        "Провайдер не смог создать изображение. "
                        "Повторите запрос позже."
                    ),
                ) from None
            _finish_success(
                settings,
                accepted,
                "Изображение создано и сохранено в проекте.",
                generated_image=prepared_image,
            )
            return
        local_answer = (
            None
            if estimate_requested
            else _try_local_conversational_answer(messages[-1]["content"])
        )
        if local_answer is not None:
            _finish_success(settings, accepted, local_answer)
            return
        widget = (
            None
            if estimate_requested
            else try_prepare_product_widget(
                settings,
                accepted,
                prompt=messages[-1]["content"],
            )
        )
        if widget is not None:
            _finish_success(
                settings,
                accepted,
                widget.fallback_text,
                widget=widget,
            )
            return
        weather_query = try_parse_weather_query(messages[-1]["content"])
        if weather_query is not None:
            try:
                weather_result = get_weather(
                    settings,
                    location=weather_query.location,
                    forecast_days=weather_query.forecast_days,
                )
            except WeatherServiceError as exc:
                _finish_error(
                    settings,
                    accepted,
                    DirectModelError("weather_service_failed", str(exc)),
                )
                return
            else:
                weather_result["providerLabel"] = "Погодный сервис"
                widget = ProductWidget(
                    arguments={
                        "location": weather_query.location,
                        "forecastDays": weather_query.forecast_days,
                    },
                    fallback_text=str(weather_result["summary"]),
                    tool_name="get_weather",
                    tool_result=weather_result,
                )
                _finish_success(
                    settings,
                    accepted,
                    widget.fallback_text,
                    widget=widget,
                )
                return
        database = connect_database(settings.database_url)
        try:
            profile, credential_tenant_id = _connected_profile(
                database,
                accepted,
                selected_profile,
            )
        finally:
            database.close()
        try:
            runtime = runtimes.require(profile)
        except AgentRuntimeError as exc:
            raise DirectModelError(exc.code, exc.message) from None
        if estimate_requested:
            skill_plan = _estimate_skill_plan_for_run(settings, accepted)
            intake_guidance = "\n\n".join(
                guidance
                for guidance in (
                    skill_plan.guidance_for_stage("project_case_analysis"),
                    skill_plan.guidance_for_stage("technology_card_build"),
                    skill_plan.guidance_for_stage("price_candidates_verify"),
                    skill_plan.guidance_for_stage("estimate_engine_calculate"),
                    skill_plan.guidance_for_stage("estimate_verification"),
                )
                if guidance
            )
            analysis_tool_call_id = _start_tool_stage(
                settings,
                accepted,
                tool_name="project_case_analysis",
                arguments={
                    "projectId": accepted.project_id,
                    "sourceMessage": messages[-1]["content"][:500],
                },
            )
            try:
                conversation = "\n\n".join(
                    f"{'Пользователь' if item['role'] == 'user' else 'Kolibri'}:"
                    f"\n{item['content']}"
                    for item in messages
                )
                request = _agent_runtime_request(
                    accepted=accepted,
                    mode="structured",
                    execution_profile="estimate-intake",
                    messages=messages,
                    credential_tenant_id=credential_tenant_id,
                    initial_prompt=(
                        "Ниже канонический снимок разговора Kolibri. "
                        "Нормализуй исходные данные для Estimate Engine.\n\n"
                        f"{conversation}"
                    ),
                    instructions=plastering_intake_instructions(
                        today=datetime.now(timezone.utc).date().isoformat(),
                        runtime_guidance=intake_guidance,
                    ),
                    timeout_seconds=settings.direct_model_timeout_seconds,
                    selection=AgentModelSelection(
                        model_id=frozen_model,
                        reasoning_effort=frozen_effort,
                        service_tier=frozen_service_tier,
                        explicit_profile=(selected_profile != "auto"),
                    ),
                    access=AgentAccessPolicy(
                        mode="standard",
                        sandbox="read-only",
                        approval_policy="never",
                    ),
                    workspace=AgentWorkspace(reference="none"),
                    output_schema=PLASTERING_INTAKE_SCHEMA,
                    guidance=intake_guidance,
                    cancellation_signal=cancellation_signal,
                )
                result = runtime.execute(request)
                intake = parse_plastering_intake(result.text or "")
                intake = normalize_plastering_intake(
                    intake,
                    prompt=str(messages[-1]["content"]),
                )
            except AgentRuntimeError as exc:
                direct_error = DirectModelError(exc.code, exc.message)
                _finish_tool_stage(
                    settings,
                    accepted,
                    tool_call_id=analysis_tool_call_id,
                    result={
                        "status": "failed",
                        "errorCode": direct_error.code,
                    },
                )
                raise direct_error from None
            except (ValueError, ValidationError):
                direct_error = DirectModelError(
                    "estimate_intake_invalid",
                    "Выбранный агент не нормализовал исходные данные сметы.",
                )
                _finish_tool_stage(
                    settings,
                    accepted,
                    tool_call_id=analysis_tool_call_id,
                    result={
                        "status": "failed",
                        "errorCode": direct_error.code,
                    },
                )
                raise direct_error from None
            except DirectModelError as exc:
                _finish_tool_stage(
                    settings,
                    accepted,
                    tool_call_id=analysis_tool_call_id,
                    result={
                        "status": "failed",
                        "errorCode": exc.code,
                    },
                )
                raise
            _finish_tool_stage(
                settings,
                accepted,
                tool_call_id=analysis_tool_call_id,
                result={
                    "status": "complete",
                    "region": intake.region,
                    "wallAreaM2": intake.wall_area_m2,
                    "averageThicknessMm": intake.average_thickness_mm,
                    "assumptionCount": len(intake.assumptions),
                },
            )
            technology_tool_call_id = _start_tool_stage(
                settings,
                accepted,
                tool_name="technology_card_build",
                arguments={
                    "rulesVersion": "plastering/1.0.0",
                    "applicationMethod": intake.application_method,
                    "material": intake.material,
                },
            )
            try:
                widget = materialize_engine_estimate_widget(
                    settings,
                    accepted,
                    intake=intake,
                    provider_profile=profile,
                )
            except RuntimeError:
                _finish_tool_stage(
                    settings,
                    accepted,
                    tool_call_id=technology_tool_call_id,
                    result={
                        "status": "failed",
                        "errorCode": "estimate_persistence_failed",
                    },
                )
                raise DirectModelError(
                    "estimate_persistence_failed",
                    "Не удалось сохранить подготовленную смету в проекте.",
                ) from None
            calculation = widget.tool_result or {}
            _finish_tool_stage(
                settings,
                accepted,
                tool_call_id=technology_tool_call_id,
                result={
                    "status": "complete",
                    "technologyStageCount": calculation.get("technologyStageCount"),
                    "rulesVersion": calculation.get("rulesVersion"),
                },
            )
            _complete_tool_stage(
                settings,
                accepted,
                tool_name="price_candidates_verify",
                arguments={
                    "candidateCount": calculation.get("candidatePriceCount"),
                    "snapshotVersion": calculation.get("priceSnapshotVersion"),
                    "policy": "independent-reference-check",
                },
                result={
                    "status": calculation.get("validationStatus"),
                    "withinReferenceRangeCount": calculation.get(
                        "candidateWithinRangeCount"
                    ),
                    "outlierCount": calculation.get("candidateOutlierCount"),
                    "unverifiedPriceCount": calculation.get("unverifiedPriceCount"),
                    "missingPriceCount": calculation.get("missingPriceCount"),
                },
            )
            _complete_tool_stage(
                settings,
                accepted,
                tool_name="estimate_engine_calculate",
                arguments={
                    "engineVersion": calculation.get("engineVersion"),
                },
                result={
                    "status": "complete",
                    "resultHash": calculation.get("resultHash"),
                    "estimateVersion": calculation.get("estimateVersion"),
                },
            )
            _complete_tool_stage(
                settings,
                accepted,
                tool_name="estimate_verification",
                arguments={"gate": "price-provenance"},
                result={
                    "status": calculation.get("validationStatus"),
                    "releaseReady": (calculation.get("validationStatus") == "passed"),
                },
            )
            _finish_success(
                settings,
                accepted,
                widget.fallback_text,
                widget=widget,
            )
            return
        text_stream = _TextRunStream(
            settings,
            accepted,
            provider=runtime.descriptor.profile_id,
        )
        conversation = "\n\n".join(
            f"{'Пользователь' if item['role'] == 'user' else 'Kolibri'}:"
            f"\n{item['content']}"
            for item in messages
        )
        request = _agent_runtime_request(
            accepted=accepted,
            mode="chat",
            execution_profile="chat",
            messages=messages,
            credential_tenant_id=credential_tenant_id,
            initial_prompt=(
                "Ниже канонический снимок разговора Kolibri. "
                "Ответь на последний запрос пользователя.\n\n"
                f"{conversation}"
            ),
            instructions=AGENT_CHAT_INSTRUCTIONS,
            timeout_seconds=settings.direct_model_timeout_seconds,
            selection=AgentModelSelection(
                model_id=frozen_model,
                reasoning_effort=frozen_effort,
                service_tier=frozen_service_tier,
                explicit_profile=(selected_profile != "auto"),
            ),
            access=AgentAccessPolicy(
                mode="standard",
                sandbox="read-only",
                approval_policy="never",
            ),
            workspace=AgentWorkspace(reference="none"),
            on_delta=text_stream.append,
            cancellation_signal=cancellation_signal,
        )
        try:
            result = runtime.execute(request)
        except AgentRuntimeError as exc:
            raise DirectModelError(exc.code, exc.message) from None
        turn = ModelTurn(
            text=result.text,
            tool_call=(
                None
                if result.tool_call is None
                else ModelToolCall(
                    name=result.tool_call.name,
                    arguments=dict(result.tool_call.arguments),
                )
            ),
        )
    except DirectModelError as exc:
        _finish_error(settings, accepted, exc)
        return

    if turn.tool_call is not None:
        if turn.tool_call.name != "get_weather":
            _finish_error(
                settings,
                accepted,
                DirectModelError(
                    "model_tool_not_supported",
                    "Модель выбрала неподдерживаемый инструмент.",
                ),
            )
            return
        try:
            weather_result = get_weather(
                settings,
                location=str(turn.tool_call.arguments["location"]),
                forecast_days=int(turn.tool_call.arguments["forecastDays"]),
            )
        except WeatherServiceError as exc:
            _finish_error(
                settings,
                accepted,
                DirectModelError("weather_service_failed", str(exc)),
            )
            return
        weather_result["providerLabel"] = "Погодный сервис"
        widget = ProductWidget(
            arguments=turn.tool_call.arguments,
            fallback_text=str(weather_result["summary"]),
            tool_name="get_weather",
            tool_result=weather_result,
        )
        _finish_success(
            settings,
            accepted,
            widget.fallback_text,
            widget=widget,
        )
        return
    if turn.text is None:
        _finish_error(
            settings,
            accepted,
            DirectModelError("model_response_empty", "Модель вернула пустой ответ."),
        )
        return
    _finish_success(
        settings,
        accepted,
        turn.text,
        text_stream=text_stream,
    )
