from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, Sequence, runtime_checkable


@dataclass(frozen=True)
class PublicSession:
    id: str
    origin: str
    expires_at: float
    current_project_id: str | None = None


@dataclass(frozen=True)
class PublicSessionIssue:
    session: PublicSession
    credential: str


@dataclass(frozen=True)
class PublicPrincipal:
    session_id: str
    origin: str


@dataclass(frozen=True)
class CoreEvent:
    sequence: int
    event_type: str
    payload: dict[str, Any]


class CoreError(Exception):
    """A classified error returned by the authoritative Core service."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 503,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retryable = retryable


@runtime_checkable
class CoreClient(Protocol):
    """Internal boundary implemented by the durable Rust/Home Core adapter."""

    async def resolve_public_session(self, credential: str) -> PublicSession | None: ...

    async def create_public_session(self, origin: str) -> PublicSessionIssue: ...

    async def create_response(
        self,
        principal: PublicPrincipal,
        request: dict[str, Any],
        *,
        idempotency_key: str,
        request_sha256: str,
    ) -> dict[str, Any]: ...

    async def get_response(
        self,
        principal: PublicPrincipal,
        response_id: str,
    ) -> dict[str, Any] | None: ...

    async def list_response_events(
        self,
        principal: PublicPrincipal,
        response_id: str,
        *,
        after: int,
        limit: int,
    ) -> Sequence[CoreEvent]: ...

    async def wait_response_events(
        self,
        principal: PublicPrincipal,
        response_id: str,
        *,
        after: int,
        timeout_seconds: float,
    ) -> Sequence[CoreEvent]: ...

    async def cancel_response(
        self,
        principal: PublicPrincipal,
        response_id: str,
        *,
        idempotency_key: str,
        request_sha256: str,
    ) -> dict[str, Any] | None: ...
