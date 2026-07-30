"""One policy and transport adapter for standard and developer Product Chat."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
import logging
import os
import socket
import sqlite3
import threading
from typing import Protocol
import uuid

from fastapi import HTTPException, Request, status

from ..agent_runtime import AgentRuntimeRegistry
from ..config import Settings
from ..direct_model_runtime import execute_direct_run
from ..direct_run_outbox import (
    DIRECT_RUN_INTERNAL_ERROR_CODE,
    DIRECT_RUN_INTERNAL_ERROR_MESSAGE,
    DirectRunClaim,
    DirectRunLeaseError,
    DirectRunLeaseHeartbeat,
    DirectRunStore,
)
from ..image_generation import resolve_image_prompt
from ..model_catalog import (
    validate_model_selection,
    validate_profile_selection,
)
from ..platform_admin import (
    PlatformPolicyError,
    enforce_chat_access_policy,
)
from ..platform_authority import (
    PlatformDeveloperAuthorityError,
    require_platform_developer_authority,
)
from ..product_widgets import is_estimate_generation_prompt
from ..schemas import AgentProfile, UserSession
from .cancellation import ActiveRunCancellationRegistry
from .models import AgUiRunInput, message_text


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PreparedChatExecution:
    execution_plane: str
    runtime_profile: str
    model_id: str | None
    reasoning_effort: str | None
    service_tier: str | None


class AcceptedRunLike(Protocol):
    tenant_id: str
    run_id: str
    execution_plane: str
    replayed: bool


class DirectRunDispatcher:
    """Process-lifetime dispatcher for the durable direct-run queue."""

    def __init__(
        self,
        *,
        settings: Settings,
        executor: ThreadPoolExecutor,
        runtime_registry: AgentRuntimeRegistry,
        cancellations: ActiveRunCancellationRegistry,
        max_inflight: int = 2,
        worker_id: str | None = None,
    ) -> None:
        self.settings = settings
        self.executor = executor
        self.runtime_registry = runtime_registry
        self.cancellations = cancellations
        self.max_inflight = max_inflight
        self.worker_id = worker_id or (
            f"direct-{socket.gethostname()}-{os.getpid()}-"
            f"{uuid.uuid4().hex[:8]}"
        )
        self.store = DirectRunStore(settings.database_url)
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._lock = threading.Lock()
        self._futures: set[Future[None]] = set()
        self._thread = threading.Thread(
            target=self._run,
            name="kolibri-direct-dispatch",
            daemon=True,
        )

    def start(self) -> None:
        if self._thread.is_alive():
            return
        self._thread.start()

    def notify(self) -> None:
        self._wake.set()

    def close(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def _inflight(self) -> int:
        with self._lock:
            return len(self._futures)

    def _finished(self, future: Future[None]) -> None:
        with self._lock:
            self._futures.discard(future)
        self._wake.set()

    def _execute(self, claim: DirectRunClaim) -> None:
        cancellation_signal = self.cancellations.register(
            claim.tenant_id,
            claim.run_id,
        )
        try:
            with DirectRunLeaseHeartbeat(
                self.store,
                claim,
                lease_seconds=self.settings.product_run_lease_seconds,
                cancellation_signal=cancellation_signal,
            ):
                execute_direct_run(
                    self.settings,
                    claim,
                    self.runtime_registry,
                    cancellation_signal=cancellation_signal,
                )
            # Every normal path must terminalize the same durable claim.
            self.store.fail_claim(
                claim,
                code=DIRECT_RUN_INTERNAL_ERROR_CODE,
                message=DIRECT_RUN_INTERNAL_ERROR_MESSAGE,
            )
        except DirectRunLeaseError:
            LOGGER.info(
                "direct run lease superseded run_id=%s",
                claim.run_id,
            )
        except BaseException:
            LOGGER.exception(
                "direct run executor crashed run_id=%s",
                claim.run_id,
            )
            self.store.fail_claim(
                claim,
                code=DIRECT_RUN_INTERNAL_ERROR_CODE,
                message=DIRECT_RUN_INTERNAL_ERROR_MESSAGE,
            )
        finally:
            self.cancellations.unregister(
                claim.tenant_id,
                claim.run_id,
                cancellation_signal,
            )

    def _submit(self, claim: DirectRunClaim) -> bool:
        try:
            future = self.executor.submit(self._execute, claim)
        except RuntimeError:
            self.store.release_unstarted(claim)
            return False
        with self._lock:
            self._futures.add(future)
        future.add_done_callback(self._finished)
        return True

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.store.recover()
                while (
                    not self._stop.is_set()
                    and self._inflight() < self.max_inflight
                ):
                    claim = self.store.claim_next(
                        worker_id=self.worker_id,
                        lease_seconds=self.settings.product_run_lease_seconds,
                    )
                    if claim is None or not self._submit(claim):
                        break
            except Exception:
                LOGGER.exception("direct run recovery cycle failed")
            self._wake.wait(self.settings.product_run_idle_seconds)
            self._wake.clear()


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def _selection(
    identity: UserSession,
    runtime_profile: str,
) -> tuple[str | None, str | None, str | None]:
    owns_selection = (
        runtime_profile != AgentProfile.AUTO.value
        and identity.preferred_model_profile is not None
        and identity.preferred_model_profile.value == runtime_profile
    )
    if not owns_selection:
        return None, None, None
    return (
        identity.preferred_model,
        identity.preferred_reasoning_effort,
        identity.preferred_service_tier,
    )


def _required_runtime_mode(
    *,
    execution_mode: str,
    prompt: str,
) -> str:
    """Translate the Product request mode into a runtime capability.

    ``standard`` is a Product access mode, not an ``AgentRuntimeMode``.
    Comparing it directly with the runtime catalog rejected every concrete
    chat profile even when that runtime correctly advertised ``chat``.
    """

    if execution_mode == "developer":
        return "developer"
    if is_estimate_generation_prompt(prompt):
        return "structured"
    return "chat"


def prepare_chat_execution(
    request: Request,
    database: sqlite3.Connection,
    *,
    settings: Settings,
    identity: UserSession,
    run_input: AgUiRunInput,
) -> PreparedChatExecution:
    """Resolve and validate the exact accepted selection once.

    ``executionMode`` controls capabilities and access policy only. The
    execution plane is selected exclusively from server configuration, so
    standard and developer requests cannot split between unrelated transports.
    """

    execution_mode = run_input.forwarded_props.execution_mode
    runtime_profile = (
        run_input.forwarded_props.agent_profile
        or identity.preferred_agent_profile.value
    )
    model_id, reasoning_effort, service_tier = _selection(
        identity,
        runtime_profile,
    )
    execution_plane = settings.chat_execution_plane(execution_mode)
    current_message = run_input.messages[-1]
    explicit_image_request = resolve_image_prompt(
        [
            {
                "role": current_message.role,
                "content": message_text(current_message),
            }
        ]
    )
    if explicit_image_request is not None and execution_plane != "direct":
        raise _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "image_generation_unavailable",
            (
                "Генерация изображений не подключена к текущему "
                "контуру выполнения."
            ),
        )

    if execution_mode == "developer":
        try:
            require_platform_developer_authority(identity)
        except PlatformDeveloperAuthorityError as exc:
            raise _error(
                exc.status_code,
                exc.code,
                exc.message,
            ) from exc
    try:
        enforce_chat_access_policy(
            database,
            identity=identity,
            execution_mode=execution_mode,
            runtime_profile=runtime_profile,
            model_id=model_id,
            # Idempotency is resolved inside ``accept_run``. Counting here
            # would reject an exact replay after the monthly limit is reached.
            enforce_run_limit=False,
        )
    except PlatformPolicyError as exc:
        raise _error(exc.status_code, exc.code, exc.message) from exc

    if execution_mode == "developer":
        if runtime_profile == AgentProfile.AUTO.value:
            raise _error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "developer_model_selection_required",
                (
                    "Для developer-режима выберите конкретный runtime."
                ),
            )

    profile = AgentProfile(runtime_profile)
    profile_catalog = validate_profile_selection(
        request,
        database,
        tenant_id=identity.tenant_id,
        profile=profile,
    )
    required_runtime_mode = _required_runtime_mode(
        execution_mode=execution_mode,
        prompt=message_text(current_message),
    )
    if (
        profile_catalog is not None
        and required_runtime_mode not in profile_catalog.modes
    ):
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "agent_mode_not_supported",
            "Выбранный runtime не поддерживает этот режим.",
        )
    if execution_plane == "home" and service_tier is not None:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "home_service_tier_unsupported",
            (
                "Logical Home пока не поддерживает замороженный service tier; "
                "снимите выбор tier или используйте direct runtime."
            ),
        )
    if (
        execution_plane == "home"
        and model_id is not None
        and reasoning_effort is None
    ):
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "home_reasoning_effort_required",
            (
                "Для выбранной модели Logical Home требует зафиксировать "
                "reasoning effort."
            ),
        )
    if model_id is not None:
        selected = validate_model_selection(
            request,
            database,
            tenant_id=identity.tenant_id,
            profile=profile,
            model=model_id,
            reasoning_effort=reasoning_effort,
            service_tier=service_tier,
        )
        if execution_mode == "developer" and not selected.selection_supported:
            raise _error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "developer_model_selection_required",
                "Runtime не публикует выбираемый каталог моделей.",
            )
    elif (
        execution_mode == "developer"
        and profile_catalog is not None
        and profile_catalog.model_selection_supported
    ):
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "developer_model_selection_required",
            "Выберите конкретную модель из каталога runtime.",
        )

    return PreparedChatExecution(
        execution_plane=execution_plane,
        runtime_profile=runtime_profile,
        model_id=model_id,
        reasoning_effort=reasoning_effort,
        service_tier=service_tier,
    )


def dispatch_chat_execution(
    request: Request,
    *,
    settings: Settings,
    accepted: AcceptedRunLike,
) -> None:
    if accepted.execution_plane == "home":
        return
    if accepted.execution_plane != "direct":
        raise _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "chat_execution_plane_invalid",
            "Контур выполнения чата настроен неверно.",
        )
    dispatcher: DirectRunDispatcher | None = getattr(
        request.app.state,
        "direct_run_dispatcher",
        None,
    )
    if dispatcher is None:
        raise _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "direct_model_runtime_unavailable",
            "Model runtime is not available.",
        )
    dispatcher.notify()
