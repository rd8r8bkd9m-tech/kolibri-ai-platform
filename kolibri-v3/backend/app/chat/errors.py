from __future__ import annotations


class ChatError(Exception):
    """A public-safe Product Chat failure."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


class InvalidRunError(ChatError):
    def __init__(self, message: str = "AG-UI run is invalid.") -> None:
        super().__init__(422, "invalid_ag_ui_run", message)


class ThreadNotFoundError(ChatError):
    def __init__(self) -> None:
        super().__init__(404, "thread_not_found", "Thread was not found.")


class ThreadHistoryConflictError(ChatError):
    def __init__(self) -> None:
        super().__init__(
            409,
            "thread_history_conflict",
            "Thread history changed. Reload it before sending another message.",
        )


class IdempotencyConflictError(ChatError):
    def __init__(self) -> None:
        super().__init__(
            409,
            "idempotency_conflict",
            "This run ID is already bound to different input.",
        )


class ChatRuntimeUnavailableError(ChatError):
    def __init__(self) -> None:
        super().__init__(
            503,
            "chat_runtime_not_configured",
            "Logical Home execution is not configured.",
        )


class ChatPolicyError(ChatError):
    pass


class DeveloperAgentAccessError(ChatError):
    def __init__(
        self,
        *,
        unavailable: bool = False,
    ) -> None:
        if unavailable:
            super().__init__(
                503,
                "developer_agent_unavailable",
                "Developer agent is not configured on this runtime.",
            )
            return
        super().__init__(
            403,
            "owner_required",
            "Owner access is required for developer agent mode.",
        )


class ProjectRuntimeBlockedError(ChatError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(409, code, message)
