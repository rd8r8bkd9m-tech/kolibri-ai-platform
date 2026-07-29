from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any


SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "Content-Type": "text/event-stream; charset=utf-8",
    "X-Accel-Buffering": "no",
}


def encode_sse(event: Mapping[str, Any]) -> str:
    sequence = int(event["sequence"])
    payload = json.dumps(
        dict(event),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return f"id: {sequence}\ndata: {payload}\n\n"


def encode_heartbeat() -> str:
    return ": heartbeat\n\n"
