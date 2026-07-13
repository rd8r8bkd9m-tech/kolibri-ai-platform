from __future__ import annotations

from typing import Any

from .store import json_loads


def response_object(row: dict[str, Any], events: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    output_text = row.get("output_text", "")
    obj = {
        "id": row["id"],
        "object": "response",
        "created_at": row["created_at"],
        "status": row["status"],
        "model": "kolibri",
        "previous_response_id": row.get("previous_response_id"),
        "metadata": json_loads(row.get("metadata_json"), {}),
        "output": ([{
            "id": f"msg_{row['id']}",
            "type": "message",
            "status": "completed" if row["status"] == "completed" else "in_progress",
            "role": "assistant",
            "content": [{"type": "output_text", "text": output_text, "annotations": []}],
        }] if output_text else []),
        "output_text": output_text,
        "error": json_loads(row.get("error_json"), None),
    }
    if events is not None:
        obj["events"] = events
    return obj
