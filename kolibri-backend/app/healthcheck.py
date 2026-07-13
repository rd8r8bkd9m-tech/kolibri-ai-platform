"""Safe live entitlement probes for server-credential provider routes.

The probe never accepts browser/consumer sessions, never returns upstream
response bodies, and records only bounded health facts used by routing.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

import httpx

from app import ai_provider
from app.providers import get_provider


def _safe_http_result(response: httpx.Response) -> dict[str, Any]:
    return {
        "ok": response.status_code == 200,
        "status": response.status_code,
    }


def _runtime_route(provider_id: str) -> dict | None:
    mapping = {
        "openai": "openai_codex",
        "mimo": "mimo",
        "deepseek": "deepseek_flash",
        "kimi_official": "kimi_code",
        "kimi_proxy_cfbt": "cfbt",
    }
    return ai_provider.PROVIDERS.get(mapping.get(provider_id, provider_id))


async def probe_provider(provider_id: str) -> Dict[str, Any]:
    """Verify credential, model entitlement and a minimal chat invocation."""
    provider = get_provider(provider_id)
    if not provider:
        return {"provider": provider_id, "status": "not_found", "error_code": "provider_not_found"}

    checked_at = datetime.now(timezone.utc).isoformat()
    base_result: dict[str, Any] = {
        "provider": provider.id,
        "name": provider.name,
        "protocol": provider.protocol,
        "checked_at": checked_at,
        "credential_source": provider.credential_source,
        "secret_exposed": False,
        "model": provider.default_model,
        "tests": {},
    }

    if provider.protocol == "codex_cli_jsonl":
        from app.codex_cli_provider import CodexCLIError, probe_codex_cli

        result = await probe_codex_cli()
        route = _runtime_route(provider.id)
        if result.get("status") == "live":
            if route is not None:
                ai_provider._record_provider_success(route)
            provider.capabilities.chat = "true"
            provider.capabilities.streaming = "true"
            provider.capabilities.models = "true"
            result["capabilities"] = {
                "chat": provider.capabilities.chat,
                "models": provider.capabilities.models,
                "streaming": provider.capabilities.streaming,
                "tools": provider.capabilities.tools,
                "json_schema": provider.capabilities.json_schema,
                "files": provider.capabilities.files,
                "batch": provider.capabilities.batch,
            }
        elif route is not None:
            ai_provider._record_provider_failure(
                route,
                CodexCLIError(str(result.get("error_code") or "codex_cli_probe_failed")),
            )
        return result

    if not provider.routing_enabled or provider.credential_source != "server_env":
        return {
            **base_result,
            "status": "unavailable",
            "entitlement": "blocked_by_policy",
            "error_code": "provider_route_not_permitted",
        }
    if not provider.api_key:
        return {
            **base_result,
            "status": "unavailable",
            "entitlement": "unverified",
            "error_code": "server_credential_missing",
        }
    if not provider.default_model:
        return {
            **base_result,
            "status": "unavailable",
            "entitlement": "unverified",
            "error_code": "provider_model_missing",
        }

    headers = {
        "Authorization": f"Bearer {provider.api_key}",
        "Content-Type": "application/json",
    }
    route = _runtime_route(provider.id)
    try:
        timeout = httpx.Timeout(20.0, connect=8.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            models_response = await client.get(f"{provider.base_url.rstrip('/')}/models", headers=headers)
            base_result["tests"]["models"] = _safe_http_result(models_response)
            if provider.protocol == "responses":
                chat_response = await client.post(
                    f"{provider.base_url.rstrip('/')}/responses",
                    headers=headers,
                    json={
                        "model": provider.default_model,
                        "input": "Reply with OK.",
                        "max_output_tokens": 8,
                        "store": False,
                    },
                )
            else:
                chat_response = await client.post(
                    f"{provider.base_url.rstrip('/')}/chat/completions",
                    headers=headers,
                    json={
                        "model": provider.default_model,
                        "messages": [{"role": "user", "content": "Reply with OK."}],
                        "max_tokens": 8,
                    },
                )
            base_result["tests"]["chat"] = _safe_http_result(chat_response)
            chat_response.raise_for_status()
            payload = chat_response.json()
            if provider.protocol == "responses":
                from app.openai_responses import parse_response

                content = str(parse_response(payload).get("content") or "").strip()
            else:
                content = str(payload["choices"][0]["message"].get("content") or "").strip()
            if not content:
                raise ValueError("provider_returned_empty_content")
    except Exception as exc:
        if route is not None:
            ai_provider._record_provider_failure(route, exc)
        failure_kind = ai_provider._safe_failure_kind(exc)
        return {
            **base_result,
            "status": "unavailable",
            "entitlement": "denied" if failure_kind in {"http_401", "http_403", "http_404"} else "unverified",
            "error_code": failure_kind,
        }

    if route is not None:
        ai_provider._record_provider_success(route)
    provider.capabilities.chat = "true"
    provider.capabilities.models = "true" if base_result["tests"]["models"]["ok"] else "unknown"
    return {
        **base_result,
        "status": "live",
        "entitlement": "granted",
        "capabilities": {
            "chat": provider.capabilities.chat,
            "models": provider.capabilities.models,
            "streaming": provider.capabilities.streaming,
            "tools": provider.capabilities.tools,
            "json_schema": provider.capabilities.json_schema,
            "files": provider.capabilities.files,
            "batch": provider.capabilities.batch,
        },
    }
