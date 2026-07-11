"""Safe SSE framing for the public Kolibri chat compatibility route.

This module deliberately does not perform provider inference.  The public
route supplies one coroutine which returns the already verified compatibility
payload.  We emit real lifecycle events around that coroutine and one complete
terminal answer; token-shaped deltas are never invented.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from collections.abc import Awaitable, Callable
from typing import Any


STREAM_SCHEMA = "kolibri.public-chat-stream.v1"
_SHA256 = re.compile(r"^[a-f0-9]{64}$")


class PublicChatStreamError(RuntimeError):
    """A normalized failure that is safe to expose on the public stream."""

    def __init__(self, code: str, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.public_message = message
        self.retryable = retryable


def stream_timeout_seconds(requested: float | None = None) -> float:
    """Return a bounded stream timeout without exposing provider settings."""

    if requested is not None:
        return min(300.0, max(1.0, float(requested)))
    try:
        configured = float(os.environ.get("KOLIBRI_PUBLIC_CHAT_STREAM_TIMEOUT_SECONDS", "180"))
    except ValueError:
        configured = 180.0
    return min(300.0, max(1.0, configured))


def _heartbeat_seconds() -> float:
    try:
        configured = float(os.environ.get("KOLIBRI_PUBLIC_CHAT_STREAM_HEARTBEAT_SECONDS", "10"))
    except ValueError:
        configured = 10.0
    return min(30.0, max(1.0, configured))


def _event(sequence: int, event: str, data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"id: {sequence}\nevent: {event}\ndata: {payload}\n\n"


def verified_public_payload(result: dict[str, Any]) -> dict[str, Any]:
    """Return an allowlisted public result only when evidence binds its text.

    ``AIProviderManager`` already rejects unverified provider results.  This
    second check is intentional at the public event boundary: it prevents a
    future compatibility adapter or test double from turning acceptance, an
    empty answer, or unrelated evidence into a terminal success event.
    """

    if not isinstance(result, dict) or result.get("model") != "kolibri":
        raise PublicChatStreamError(
            "verification_failed",
            "Kolibri could not produce a verified answer",
        )
    answer = result.get("response")
    if not isinstance(answer, str) or not answer.strip():
        raise PublicChatStreamError(
            "verification_failed",
            "Kolibri could not produce a verified answer",
        )
    technical = result.get("technical")
    routing = technical.get("provider_routing") if isinstance(technical, dict) else None
    evidence = routing.get("evidence") if isinstance(routing, dict) else None
    if not isinstance(evidence, list):
        raise PublicChatStreamError(
            "verification_failed",
            "Kolibri could not produce a verified answer",
        )

    encoded = answer.encode("utf-8")
    output_sha256 = hashlib.sha256(encoded).hexdigest()
    provider_evidence = next((
        item
        for item in evidence
        if isinstance(item, dict)
        and item.get("type") == "provider_execution"
        and item.get("exit_code") == 0
        and item.get("output_sha256") == output_sha256
        and item.get("output_bytes") == len(encoded)
    ), None)
    verifier_evidence = next((
        item
        for item in evidence
        if isinstance(item, dict)
        and item.get("type") == "deterministic_verifier"
        and item.get("verdict") == "passed"
        and isinstance(item.get("binding_sha256"), str)
        and _SHA256.fullmatch(item["binding_sha256"].lower())
    ), None)
    if provider_evidence is None or verifier_evidence is None:
        raise PublicChatStreamError(
            "verification_failed",
            "Kolibri could not produce a verified answer",
        )

    # Technical routing, runner identity, node references, endpoints and raw
    # evidence stay server-side.  Only the content-bound verification result is
    # public.  Typed task envelopes are produced by vertical_tasks.py and are
    # already allowlisted/materialization-gated for the public Shell.
    payload: dict[str, Any] = {
        "response": answer,
        "model": "kolibri",
        "cached": bool(result.get("cached", False)),
        "verification": {
            "status": "passed",
            "output_sha256": output_sha256,
            "binding_sha256": verifier_evidence["binding_sha256"].lower(),
        },
    }
    if isinstance(result.get("task"), dict):
        payload["task"] = result["task"]
    return payload


async def public_chat_event_stream(
    *,
    stream_id: str,
    execution_mode: str,
    execute: Callable[[], Awaitable[dict[str, Any]]],
    timeout_seconds: float,
):
    """Yield accepted/progress and exactly one terminal public event.

    ``StreamingResponse`` owns the ASGI disconnect listener and cancels this
    iterator when the client closes the fetch.  We propagate that cancellation
    to the execution coroutine.  The provider gateway retains its own bounded
    execution timeout and, on the canonical Home route, cancels a timed-out
    fenced task through the Control Plane API.
    """

    common = {
        "schema_version": STREAM_SCHEMA,
        "stream_id": stream_id,
        "model": "kolibri",
        "execution_mode": execution_mode,
    }
    sequence = 1
    yield _event(sequence, "accepted", {
        **common,
        "type": "response.accepted",
        "status": "accepted",
    })
    execution_task = asyncio.create_task(execute())
    try:
        sequence += 1
        yield _event(sequence, "progress", {
            **common,
            "type": "response.progress",
            "status": "running",
            "stage": "execution",
        })

        loop = asyncio.get_running_loop()
        deadline = loop.time() + stream_timeout_seconds(timeout_seconds)
        timed_out = False
        while not execution_task.done():
            remaining = deadline - loop.time()
            if remaining <= 0:
                timed_out = True
                break
            done, _ = await asyncio.wait(
                {execution_task},
                timeout=min(_heartbeat_seconds(), remaining),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if execution_task in done:
                break
            if loop.time() >= deadline:
                timed_out = True
                break
            # SSE comments are transport keep-alives, not synthetic model
            # tokens or unverifiable execution claims.
            yield ": keep-alive\n\n"

        if timed_out:
            execution_task.cancel()
            await asyncio.gather(execution_task, return_exceptions=True)
            sequence += 1
            yield _event(sequence, "timeout", {
                **common,
                "type": "response.failed",
                "status": "failed",
                "error": {
                    "code": "timeout",
                    "message": "Kolibri did not finish within the allowed time",
                    "retryable": True,
                },
            })
            sequence += 1
            yield _event(sequence, "done", {
                **common,
                "type": "response.done",
                "status": "failed",
            })
            return

        result = await execution_task
        public_result = verified_public_payload(result)
        sequence += 1
        yield _event(sequence, "completed", {
            **common,
            "type": "response.completed",
            "status": "completed",
            **public_result,
        })
        sequence += 1
        yield _event(sequence, "done", {
            **common,
            "type": "response.done",
            "status": "completed",
        })
    except PublicChatStreamError as exc:
        sequence += 1
        yield _event(sequence, "failed", {
            **common,
            "type": "response.failed",
            "status": "failed",
            "error": {
                "code": exc.code,
                "message": exc.public_message,
                "retryable": exc.retryable,
            },
        })
        sequence += 1
        yield _event(sequence, "done", {
            **common,
            "type": "response.done",
            "status": "failed",
        })
    except asyncio.CancelledError:
        execution_task.cancel()
        await asyncio.gather(execution_task, return_exceptions=True)
        raise
    except Exception:
        # Provider stderr, exception messages and upstream bodies are never
        # serialized into a public event.
        sequence += 1
        yield _event(sequence, "failed", {
            **common,
            "type": "response.failed",
            "status": "failed",
            "error": {
                "code": "provider_unavailable",
                "message": "Kolibri could not produce a verified answer",
                "retryable": True,
            },
        })
        sequence += 1
        yield _event(sequence, "done", {
            **common,
            "type": "response.done",
            "status": "failed",
        })
    finally:
        if not execution_task.done():
            execution_task.cancel()
            await asyncio.gather(execution_task, return_exceptions=True)
