#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from kolibri_v2.app import create_app

root = Path(__file__).resolve().parents[1]
out = root / "packages/contracts/openapi.json"
out.parent.mkdir(parents=True, exist_ok=True)
schema = create_app().openapi()
components = schema.setdefault("components", {})
security_schemes = components.setdefault("securitySchemes", {})
security_schemes.update(
    {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "sk-kolibri API key or signed Kolibri session",
            "description": "OpenAI-compatible bearer authentication.",
        },
        "KolibriSessionCookie": {
            "type": "apiKey",
            "in": "cookie",
            "name": "kolibri_session",
            "description": "Secure HttpOnly browser session cookie.",
        },
        "KolibriSessionHeader": {
            "type": "apiKey",
            "in": "header",
            "name": "X-Kolibri-Session",
        },
        "KolibriNodeToken": {
            "type": "apiKey",
            "in": "header",
            "name": "X-Kolibri-Node-Token",
        },
    }
)

public_paths = {"/health", "/ready", "/api/health", "/api/ready", "/v1/shell/bootstrap"}
node_paths = (
    "/v1/nodes/register",
    "/v1/nodes/{node_id}/heartbeat",
    "/v1/tasks/lease",
    "/v1/tasks/{task_id}/heartbeat",
    "/v1/tasks/{task_id}/artifacts",
    "/v1/tasks/{task_id}/complete",
    "/v1/tasks/{task_id}/fail",
)
for path, path_item in schema.get("paths", {}).items():
    for method, operation in path_item.items():
        if method.lower() not in {"get", "post", "put", "patch", "delete"} or not isinstance(operation, dict):
            continue
        parameters = operation.get("parameters", [])
        operation["parameters"] = [
            parameter
            for parameter in parameters
            if str(parameter.get("name", "")).lower()
            not in {"authorization", "x-kolibri-session", "kolibri_session"}
        ]
        if path in public_paths:
            operation.pop("security", None)
        elif path in node_paths:
            operation["security"] = [{"KolibriNodeToken": []}]
        elif path.startswith("/v1"):
            operation["security"] = [
                {"BearerAuth": []},
                {"KolibriSessionCookie": []},
                {"KolibriSessionHeader": []},
            ]

schema.setdefault("x-kolibri-openai-compatibility", {})["matrix"] = "openai-compatibility.json"
schema["x-kolibri-openai-compatibility"]["generic_provider_gateway"] = "/v1/{resource_path}"
out.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"wrote {out}")
