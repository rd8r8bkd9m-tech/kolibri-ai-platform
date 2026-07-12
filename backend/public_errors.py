"""Stable, non-secret errors for public model execution surfaces.

Provider routing contains operator-only details such as runner names, node
identities, upstream bodies and endpoints.  Public APIs still need to explain
why a request did not complete.  This module reduces the private routing trace
to a bounded reason and aggregate attempt counts without serialising the raw
trace or a catch-all failure sentence.
"""

from __future__ import annotations

from typing import Any


def _routing(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    technical = value.get("technical")
    if isinstance(technical, dict) and isinstance(technical.get("provider_routing"), dict):
        return technical["provider_routing"]
    routing = value.get("provider_routing")
    if isinstance(routing, dict):
        return routing
    return value


def _private_reason(routing: dict[str, Any]) -> str:
    value = str(routing.get("error_type") or "").strip().lower()
    if value:
        return value
    attempts = routing.get("attempts") if isinstance(routing.get("attempts"), list) else []
    for attempt in reversed(attempts):
        if isinstance(attempt, dict) and attempt.get("error_type"):
            return str(attempt["error_type"]).strip().lower()
    return ""


def _public_reason(reason: str, *, attempt_count: int) -> tuple[str, str, bool]:
    if any(marker in reason for marker in ("timeout", "deadline")):
        return (
            "provider_timeout",
            "The configured model routes reached their execution deadline before one completed.",
            True,
        )
    if any(marker in reason for marker in (
        "no_fresh", "no_capable", "capacity", "overload", "lease_unavailable",
    )):
        return (
            "provider_capacity_unavailable",
            "No eligible model worker was available for this request.",
            True,
        )
    if any(marker in reason for marker in ("auth", "permission", "forbidden")):
        return (
            "provider_route_authorization_failed",
            "The execution service rejected authorization for the configured model route.",
            False,
        )
    if any(marker in reason for marker in ("evidence", "verif", "empty_output", "invalid_output")):
        return (
            "provider_result_rejected",
            "A model route returned data, but the result did not pass the output evidence checks.",
            False,
        )
    if any(marker in reason for marker in ("cancel", "lease", "interrupt")):
        return (
            "provider_execution_interrupted",
            "Model execution ended before a completed result was recorded.",
            True,
        )
    if any(marker in reason for marker in (
        "unavailable", "connection", "endpoint", "control", "transport", "http",
    )):
        return (
            "provider_service_unavailable",
            "The model execution service was unavailable, so the request did not start or complete.",
            True,
        )
    if attempt_count == 0:
        return (
            "provider_routes_unavailable",
            "No configured model route could be started for this request.",
            True,
        )
    return (
        "provider_routes_exhausted",
        "The configured model routes ended without a completed result.",
        True,
    )


def public_provider_failure(value: Any) -> dict[str, Any]:
    """Return a truthful allowlisted provider-exhaustion envelope."""

    routing = _routing(value)
    attempts = routing.get("attempts") if isinstance(routing.get("attempts"), list) else []
    attempts = [item for item in attempts if isinstance(item, dict)]
    reason = _private_reason(routing)
    code, message, retryable = _public_reason(reason, attempt_count=len(attempts))
    timed_out = sum(
        1 for item in attempts
        if "timeout" in str(item.get("error_type") or "").lower()
        or "deadline" in str(item.get("error_type") or "").lower()
    )
    cancelled = sum(
        1 for item in attempts
        if str(item.get("status") or "").lower() in {"cancelled", "canceled"}
    )
    failed = sum(
        1 for item in attempts
        if str(item.get("status") or "").lower() in {"failed", "error"}
    )
    skipped = sum(
        1 for item in attempts
        if str(item.get("status") or "").lower() == "skipped"
    )
    return {
        "type": "provider_unavailable",
        "code": code,
        "message": message,
        "retryable": retryable,
        "attempt_summary": {
            "attempted": len(attempts),
            "failed": failed,
            "timed_out": timed_out,
            "cancelled": cancelled,
            "skipped": skipped,
        },
    }


def public_verification_failure() -> dict[str, Any]:
    """Explain why an unbound answer was withheld without leaking its text."""

    return {
        "type": "response_verification_failed",
        "code": "verification_failed",
        "message": "The response was withheld because its output could not be matched to execution evidence.",
        "retryable": False,
    }


def public_execution_failure() -> dict[str, Any]:
    """Return a safe error for a server-side failure outside provider routing."""

    return {
        "type": "response_internal_error",
        "code": "response_internal_error",
        "message": "The server encountered an internal execution error before the response completed.",
        "retryable": True,
    }
