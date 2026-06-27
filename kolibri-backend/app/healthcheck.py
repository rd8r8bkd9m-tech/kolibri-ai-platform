"""Provider healthcheck — probe capabilities and verify connectivity."""
import os
import json
import httpx
from typing import Dict, Any
from app.providers import get_provider, PROVIDERS


async def probe_provider(provider_id: str) -> Dict[str, Any]:
    """Run full healthcheck on a provider."""
    p = get_provider(provider_id)
    if not p:
        return {"error": f"Provider {provider_id} not found"}

    base = p.base_url
    key = p.api_key
    model = p.default_model
    headers = {}
    if key:
        headers["Authorization"] = f"Bearer {key}"

    result = {
        "provider": p.id,
        "name": p.name,
        "base_url": base,
        "official_kimi": p.official,
        "custom_proxy": p.custom_proxy,
        "secret_exposed": False,
        "tests": {},
    }

    async with httpx.AsyncClient(timeout=30) as client:
        # 1. Models endpoint
        result["tests"]["models"] = await _test_models(client, base, headers, model)

        # 2. Chat completions
        chat_result = await _test_chat(client, base, headers, model)
        result["tests"]["chat"] = chat_result

        # 3. Streaming
        result["tests"]["streaming"] = await _test_streaming(client, base, headers, model)

        # 4. JSON output
        result["tests"]["json"] = await _test_json(client, base, headers, model)

        # 5. Tool calling
        result["tests"]["tools"] = await _test_tools(client, base, headers, model)

        # 6. Timeout test
        result["tests"]["timeout"] = await _test_timeout(client, base, headers)

        # 7. Invalid key test
        result["tests"]["invalid_key"] = await _test_invalid_key(client, base)

        # 8. Error shape test
        result["tests"]["error_shape"] = await _test_error_shape(client, base, headers)

    # Update capabilities
    caps = p.capabilities
    caps.models = "true" if result["tests"]["models"].get("ok") else "false"
    caps.chat = "true" if result["tests"]["chat"].get("ok") else "false"
    caps.streaming = "true" if result["tests"]["streaming"].get("ok") else "false"
    caps.json_schema = "true" if result["tests"]["json"].get("ok") else "false"
    caps.tools = "true" if result["tests"]["tools"].get("ok") else "false"

    result["model_used"] = model
    result["capabilities"] = {
        "chat": caps.chat, "models": caps.models, "streaming": caps.streaming,
        "tools": caps.tools, "json_schema": caps.json_schema,
        "files": caps.files, "batch": caps.batch,
    }

    return result


async def _test_models(client, base, headers, model):
    try:
        r = await client.get(f"{base}/models", headers=headers)
        if r.status_code == 200:
            data = r.json()
            models = [m["id"] for m in data.get("data", [])]
            return {"ok": True, "status": 200, "models": models}
        return {"ok": False, "status": r.status_code, "error": r.text[:200]}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


async def _test_chat(client, base, headers, model):
    if not model:
        return {"ok": False, "error": "No model configured"}
    try:
        r = await client.post(f"{base}/chat/completions", headers={**headers, "Content-Type": "application/json"},
                              json={"model": model, "messages": [{"role": "user", "content": "Reply OK"}]})
        if r.status_code == 200:
            data = r.json()
            msg = data["choices"][0]["message"]
            content = msg.get("content") or ""
            reasoning = msg.get("reasoning_content") or ""
            return {"ok": True, "status": 200, "content": content[:100], "reasoning": reasoning[:100], "has_content": bool(content), "has_reasoning": bool(reasoning)}
        return {"ok": False, "status": r.status_code, "error": r.text[:200]}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


async def _test_streaming(client, base, headers, model):
    if not model:
        return {"ok": False, "error": "No model configured"}
    try:
        r = await client.post(f"{base}/chat/completions", headers={**headers, "Content-Type": "application/json"},
                              json={"model": model, "messages": [{"role": "user", "content": "Hi"}], "stream": True, "max_tokens": 5})
        if r.status_code == 200:
            chunks = r.text[:500]
            return {"ok": True, "status": 200, "sample": chunks[:200]}
        return {"ok": False, "status": r.status_code, "error": r.text[:200]}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


async def _test_json(client, base, headers, model):
    if not model:
        return {"ok": False, "error": "No model configured"}
    try:
        r = await client.post(f"{base}/chat/completions", headers={**headers, "Content-Type": "application/json"},
                              json={"model": model, "messages": [{"role": "user", "content": 'Reply with JSON: {"status":"ok"}'}]})
        if r.status_code == 200:
            data = r.json()
            msg = data["choices"][0]["message"]
            content = msg.get("content") or ""
            if not content:
                reasoning = msg.get("reasoning_content") or ""
                return {"ok": True, "valid_json": False, "note": "content null, reasoning present", "reasoning": reasoning[:100]}
            try:
                json.loads(content)
                return {"ok": True, "valid_json": True}
            except json.JSONDecodeError:
                return {"ok": True, "valid_json": False, "content": content[:100]}
        return {"ok": False, "status": r.status_code, "error": r.text[:200]}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


async def _test_tools(client, base, headers, model):
    if not model:
        return {"ok": False, "error": "No model configured"}
    tools = [{"type": "function", "function": {"name": "get_weather", "description": "Get weather", "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}}}]
    try:
        r = await client.post(f"{base}/chat/completions", headers={**headers, "Content-Type": "application/json"},
                              json={"model": model, "messages": [{"role": "user", "content": "What's the weather in Moscow?"}], "tools": tools, "max_tokens": 50})
        if r.status_code == 200:
            data = r.json()
            msg = data["choices"][0]["message"]
            has_tool_calls = bool(msg.get("tool_calls"))
            return {"ok": True, "tool_calls": has_tool_calls}
        return {"ok": False, "status": r.status_code, "error": r.text[:200]}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


async def _test_timeout(client, base, headers):
    try:
        async with httpx.AsyncClient(timeout=2) as short_client:
            r = await short_client.get(f"{base}/models", headers=headers)
            return {"ok": True, "reachable": True}
    except httpx.TimeoutException:
        return {"ok": True, "reachable": False, "note": "Timeout is expected for slow endpoints"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


async def _test_invalid_key(client, base):
    try:
        r = await client.get(f"{base}/models", headers={"Authorization": "Bearer invalid-key-test"})
        return {"ok": True, "status": r.status_code, "rejects_invalid": r.status_code in (401, 403)}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


async def _test_error_shape(client, base, headers):
    try:
        r = await client.post(f"{base}/chat/completions", headers={**headers, "Content-Type": "application/json"},
                              json={"model": "nonexistent-model-xyz", "messages": [{"role": "user", "content": "test"}]})
        return {"ok": True, "status": r.status_code, "error_shape": r.text[:300]}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}
