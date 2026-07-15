"""AI provider — multi-model auto-routing for Kolibri."""
from copy import deepcopy
import os
import json
import time
from datetime import datetime, timezone
from html import escape
import httpx
from typing import List, Dict, Optional

from app.estimate_action import (
    build_estimate_action,
    ensure_estimate_action,
    is_estimate_request,
    latest_user_text,
)

AI_TIMEOUT = int(os.getenv("AI_TIMEOUT", "60"))
PROVIDER_FAILURE_COOLDOWN_SECONDS = int(os.getenv("PROVIDER_FAILURE_COOLDOWN_SECONDS", "60"))
PROVIDER_AUTH_COOLDOWN_SECONDS = int(os.getenv("PROVIDER_AUTH_COOLDOWN_SECONDS", "300"))
_provider_blocked_until: Dict[str, float] = {}
_provider_route_state: Dict[str, dict] = {}

# Provider configs — ordered by speed (fastest first)
PROVIDERS = {
    "codex_cli": {
        "id": "codex_cli",
        "url": (
            "home://control-plane"
            if os.getenv("KOLIBRI_FACTORY_RESPONSES_ENABLED", "").lower()
            in {"1", "true", "yes", "on"}
            else "local://codex-cli"
        ),
        "model": os.getenv("CODEX_CLI_MODEL", "") or os.getenv("KOLIBRI_CODEX_MODEL", "") or "account-default",
        "key": "",
        "protocol": (
            "home_factory"
            if os.getenv("KOLIBRI_FACTORY_RESPONSES_ENABLED", "").lower()
            in {"1", "true", "yes", "on"}
            else "codex_cli"
        ),
        "credential_source": (
            "home_control_plane"
            if os.getenv("KOLIBRI_FACTORY_RESPONSES_ENABLED", "").lower()
            in {"1", "true", "yes", "on"}
            else "home_codex_cli_login"
        ),
        "routable": os.getenv("CODEX_CLI_ENABLED", "true").lower() in {"1", "true", "yes", "on"},
        "cost": "owner_subscription",
        "speed_ms": 0,
        "speed": "adaptive",
        "quality": "best",
    },
    "openai_codex": {
        "id": "openai_codex",
        "url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/") + "/responses",
        "model": os.getenv("OPENAI_MODEL", "gpt-5.6-sol"),
        "key": os.getenv("OPENAI_API_KEY", ""),
        "protocol": "responses",
        "credential_source": "server_env",
        "routable": os.getenv("OPENAI_REST_ROUTING_ENABLED", "").lower() in {"1", "true", "yes", "on"},
        "cost": "high",
        "speed_ms": 0,
        "speed": "adaptive",
        "quality": "best",
    },
    "kimi_code": {
        "id": "kimi_code",
        "url": os.getenv("KIMI_BASE_URL", "https://api.moonshot.ai/v1") + "/chat/completions",
        "model": os.getenv("KIMI_MODEL", "kimi-k2.7-code"),
        "key": os.getenv("KIMI_API_KEY", ""),
        "credential_source": "server_env",
        "routable": True,
        "cost": "medium",
        "speed_ms": 1700,
        "speed": "fastest",
        "quality": "best",
    },
    "deepseek_pro": {
        "id": "deepseek_pro",
        "url": os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com") + "/chat/completions",
        "model": "deepseek-v4-pro",
        "key": os.getenv("DEEPSEEK_API_KEY", ""),
        "credential_source": "server_env",
        "routable": True,
        "cost": "low",
        "speed_ms": 2300,
        "speed": "fast",
        "quality": "best",
    },
    "mimo": {
        "id": "mimo",
        "url": os.getenv("MIMO_BASE_URL", "https://token-plan-sgp.xiaomimimo.com/v1") + "/chat/completions",
        "model": os.getenv("MIMO_MODEL", "mimo-v2.5-pro"),
        "key": os.getenv("MIMO_API_KEY", ""),
        "credential_source": "server_env",
        "routable": True,
        "cost": "free",
        "speed_ms": 3300,
        "speed": "medium",
        "quality": "good",
    },
    "deepseek_flash": {
        "id": "deepseek_flash",
        "url": os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com") + "/chat/completions",
        "model": "deepseek-v4-flash",
        "key": os.getenv("DEEPSEEK_API_KEY", ""),
        "credential_source": "server_env",
        "routable": True,
        "cost": "low",
        "speed_ms": 3500,
        "speed": "medium",
        "quality": "good",
    },
    "cfbt": {
        "id": "cfbt",
        "url": os.getenv("KIMI_CFBT_BASE_URL", "https://cfbt.ccwu.cc/v1") + "/chat/completions",
        "model": os.getenv("KIMI_CFBT_MODEL", "@cf/moonshotai/kimi-k2.6"),
        "key": os.getenv("KIMI_CFBT_API_KEY", ""),
        "credential_source": "server_env",
        "routable": True,
        "cost": "free",
        "speed_ms": 3900,
        "speed": "slow",
        "quality": "good",
    },
    "kimi_fast": {
        "id": "kimi_fast",
        "url": os.getenv("KIMI_BASE_URL", "https://api.moonshot.ai/v1") + "/chat/completions",
        "model": "kimi-k2.7-code-highspeed",
        "key": os.getenv("KIMI_API_KEY", ""),
        "credential_source": "server_env",
        "routable": True,
        "cost": "high",
        "speed_ms": 1800,
        "speed": "fastest",
        "quality": "good",
    },
    "deepseek_local": {
        "id": "deepseek_local",
        "url": "http://127.0.0.1:8000/deepseek/chat/completions",
        "model": os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
        "key": "",
        "credential_source": "internal_service",
        "routable": False,
        "cost": "low",
        "speed_ms": 3500,
        "speed": "medium",
        "quality": "good",
    },
}

SOLO_BEHAVIOR_PROMPT = """Режим автономного универсального исполнителя:
1. Сам определи тип задачи и выбери только реально доступный маршрут.
2. Уточняй минимум: если безопасное разумное предположение позволяет продолжить,
   зафиксируй его и выполни задачу. Спрашивай только о блокирующих данных.
3. До обещания действия проверь capability/инструмент. Не имитируй выполнение:
   файл считается созданным только после записи, источник — проверенным только
   после реального поиска, API — вызванным только после вызова, артефакт — готовым
   только после получения bytes/hash, а смета — рассчитанной только backend-движком.
4. Многошаговую задачу доводи до практически полезного результата в текущем
   сеансе. Не перекладывай на пользователя то, что можешь выполнить сам.
5. Для свежих данных используй веб-поиск и источники; для проекта — реальное
   чтение файлов. Не выдумывай содержимое, доступ или результат инструмента.
6. Внутренний план используй для выполнения, но не раскрывай private reasoning.
   Пользователю показывай только безопасный Work Trace, проверки и итог.
7. При недоступности сообщи: что недоступно, проверяемую причину и ближайший
   реально выполнимый вариант. Используй формат: «Недоступно в текущем сеансе:
   <что именно>. Причина: <нет инструмента/нет доступа/нет данных>. Могу вместо
   этого: <реальный ближайший вариант>». Не выдавай черновик за завершённый результат.
8. Если действие доступно, выполняй его без лишнего подтверждения. Подтверждение
   запрашивай только перед рискованным, необратимым, финансовым действием либо
   когда необходимы персональные данные или отдельное разрешение владельца.

Приоритет: точность и проверяемость выше скорости и красивой формулировки;
готовый подтверждённый результат выше обещаний; безопасность выше имитации."""

SYSTEM_PROMPT = """Ты — Колибри, универсальная AI-операционная система и единый интерфейс пользователя.
Ты помогаешь превращать обычную фразу в проверенный результат: ответ, исследование,
смету, документ, изображение, код, сайт, приложение или автоматизацию — но только
через реально доступные и разрешённые возможности текущего сеанса.

Ты являешься Колибри при любом внутреннем исполнителе. Никогда не представляйся
DeepSeek, Mimo, Codex, строительным ассистентом или другой ограниченной моделью.
Внутренний исполнитель не имеет права переопределять твою идентичность, область
задач или заявлять, что функция выполнена. Возможность считается доступной только
если она перечислена ниже как invocable/live. Если нужного маршрута нет, сообщи
структурированную недоступность; не выдумывай результат, файл, источник или действие.

Когда пользователь просит создать смету — верни только JSON-действие в формате:
```json
{"action":"create_estimate","title":"...","object_name":"...","region":"город, регион","assumptions":["..."],"questions":["..."],"sections":[{"title":"...","positions":[{"code":"код КСР/ресурса, только если уверен; иначе пусто","name":"точное индивидуальное наименование ресурса или работы","unit":"...","quantity":"...","price":"0","comment":"основание количества"}]}]}
```
Не используй укрупнённый фиксированный шаблон. Сформируй индивидуальную ведомость
по запросу: отдельные ресурсы, работы, машины и труд. Не выдумывай коды КСР,
цены и источники. Оставляй price равным 0: backend сам подберёт последний реально
опубликованный региональный период ФГИС ЦС, проверит код, единицу, НДС и формулу.
Неподтверждённые строки останутся без цены, а все суммы пересчитает Decimal-движок.

Когда просит создать документ — верни:
```json
{"action": "create_document", "title": "...", "type": "contract|act|proposal|report|memo|letter", "content": "Полный текст документа без Markdown и HTML"}
```

Когда нужна информация из интернета — используй веб-поиск.
Когда ищешь в документах — используй локальный поиск.

Отвечай на русском. Будь краток и практичен."""


def _live_capability_names() -> list[str]:
    try:
        from app.capability_runtime import capability_snapshot

        catalog = capability_snapshot()
        return [
            str(item.get("name") or item.get("id"))
            for item in catalog.get("capabilities", [])
            if isinstance(item, dict)
            and item.get("status") == "available"
            and item.get("invocable") is True
        ]
    except Exception:
        return []


def _kolibri_system_prompt() -> str:
    """Bind self-description to the live capability catalog, not provider lore."""
    live = _live_capability_names()
    capability_context = (
        "Подтверждённые доступные возможности этого сеанса: " + ", ".join(live) + "."
        if live
        else "Подтверждённые invocable-возможности этого сеанса не обнаружены. Не заявляй обратное."
    )
    return f"{SYSTEM_PROMPT}\n\n{SOLO_BEHAVIOR_PROMPT}\n\n{capability_context}"


def _compose_system_prompt(specialization: Optional[str] = None) -> str:
    """Add a task specialization without dropping Kolibri/Solo invariants."""

    base = _kolibri_system_prompt()
    if not specialization:
        return base
    return (
        f"{base}\n\nДополнительная специализация для текущей задачи:\n"
        f"{specialization.strip()}\n\n"
        "Эта специализация не отменяет идентичность Колибри, проверку capabilities, "
        "запрет имитации и остальные правила режима Solo."
    )


def _is_self_description_request(messages: List[Dict[str, str]]) -> bool:
    prompt = next(
        (str(message.get("content") or "") for message in reversed(messages) if message.get("role") == "user"),
        "",
    ).strip().lower()
    prefixes = (
        "кто ты",
        "что ты умеешь",
        "что умеешь",
        "какие у тебя возможности",
        "расскажи о своих возможностях",
        "who are you",
        "what can you do",
    )
    return any(prompt.startswith(prefix) for prefix in prefixes)


def _capability_self_description() -> dict:
    from app.capability_registry import capability_self_description
    from app.capability_runtime import capability_snapshot

    description = capability_self_description(capability_snapshot())
    return {
        "content": description["content"],
        "reasoning": "",
        "actions": [],
        "status": description["status"],
        "provider": "kolibri_catalog",
        "model": "kolibri.capabilities.v1",
        "speed_ms": 0,
        "fallback_used": False,
        "capabilities": description["capabilities"],
        "as_of": description["as_of"],
    }


async def _image_completion_if_requested(
    messages: List[Dict[str, str]],
    policy: Optional[dict],
    *,
    run_id: Optional[str] = None,
) -> dict | None:
    """Defense-in-depth: image intent never falls through to a text model."""
    from app.image_artifacts import (
        IMAGE_CAPABILITY_ID,
        ImageCapabilityUnavailable,
        ImageGenerationFailed,
        ImageGenerationRequest,
        generate_invocable_image,
        image_execution_identity,
        is_image_generation_request,
    )

    prompt = next(
        (str(message.get("content") or "") for message in reversed(messages) if message.get("role") == "user"),
        "",
    )
    if not is_image_generation_request(prompt):
        return None
    try:
        artifact = await generate_invocable_image(
            ImageGenerationRequest(prompt=prompt),
            policy=policy,
            run_id=run_id,
        )
    except ImageCapabilityUnavailable:
        return {
            "content": "Генерация изображений сейчас недоступна.",
            "reasoning": "",
            "actions": [],
            "status": "capability_unavailable",
            "provider": "none",
            "model": "none",
            "fallback_used": False,
            "error_code": "capability_unavailable",
            "recoverable": True,
            "capability": IMAGE_CAPABILITY_ID,
        }
    except ImageGenerationFailed:
        image_identity = image_execution_identity()
        return {
            "content": "Изображение не создано: файл не прошёл проверку.",
            "reasoning": "",
            "actions": [],
            "status": "failed",
            "provider": image_identity["provider"],
            "model": image_identity["model"],
            "fallback_used": False,
            "error_code": "image_artifact_verification_failed",
            "recoverable": True,
            "capability": IMAGE_CAPABILITY_ID,
        }
    image_identity = image_execution_identity()
    return {
        "content": "Изображение создано и сохранено в текущем проекте.",
        "reasoning": "",
        "actions": [{"type": "present_image", "label": "Открыть изображение", "data": artifact}],
        "status": "ready",
        "provider": image_identity["provider"],
        "model": artifact["model"],
        "fallback_used": False,
    }


def _provider_id(provider: dict) -> str:
    return str(provider.get("id") or provider.get("model") or "unknown")


def _provider_is_configured(name: str, provider: dict) -> bool:
    if not provider.get("routable", True):
        return False
    if provider.get("protocol") == "codex_cli":
        from app.codex_cli_provider import codex_cli_configuration

        return bool(codex_cli_configuration().get("configured"))
    if provider.get("protocol") == "home_factory":
        from app.home_factory_response import factory_response_configuration

        return bool(factory_response_configuration().get("configured"))
    if provider.get("credential_source") != "server_env":
        return False
    if not provider.get("key") or not provider.get("model") or not provider.get("url"):
        return False
    if name == "cfbt" and os.getenv("KIMI_CFBT_ENABLED", "").lower() not in {"1", "true", "yes"}:
        return False
    return True


def _provider_is_healthy(provider: dict) -> bool:
    from app.capability_runtime import capability_release_id

    state = _provider_route_state.get(_provider_id(provider), {})
    if state.get("release_id") != capability_release_id():
        return True
    return _provider_blocked_until.get(_provider_id(provider), 0) <= time.monotonic()


def _record_provider_success(provider: dict) -> None:
    from app.capability_runtime import capability_release_id

    provider_id = _provider_id(provider)
    verified_at = datetime.now(timezone.utc).isoformat()
    _provider_blocked_until.pop(provider_id, None)
    _provider_route_state[provider_id] = {
        "release_id": capability_release_id(),
        "status": "live",
        "verified_at": verified_at,
        "failure_kind": None,
    }
    # Persist only the sanitised verdict; prompts and provider output never
    # enter the capability evidence ledger.
    from app.capability_runtime import record_capability_invocation

    record_capability_invocation(
        "chat.responses",
        succeeded=True,
        provider=provider_id,
        model=str(provider.get("model") or ""),
        evidence_id=f"provider:{provider_id}:{verified_at}",
    )


def _record_provider_failure(provider: dict, error: Exception) -> None:
    from app.capability_runtime import capability_release_id

    cooldown = PROVIDER_FAILURE_COOLDOWN_SECONDS
    status_code = error.response.status_code if isinstance(error, httpx.HTTPStatusError) else None
    if status_code in {401, 403}:
        cooldown = PROVIDER_AUTH_COOLDOWN_SECONDS
    provider_id = _provider_id(provider)
    _provider_blocked_until[provider_id] = time.monotonic() + cooldown
    _provider_route_state[provider_id] = {
        "release_id": capability_release_id(),
        "status": "blocked",
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "failure_kind": _safe_failure_kind(error),
    }


def _safe_failure_kind(error: Exception) -> str:
    safe_kind = getattr(error, "failure_kind", None)
    if isinstance(safe_kind, str) and safe_kind.startswith("codex_cli_"):
        return safe_kind
    if isinstance(error, httpx.HTTPStatusError):
        return f"http_{error.response.status_code}"
    if isinstance(error, httpx.TimeoutException):
        return "timeout"
    if isinstance(error, httpx.RequestError):
        return "network_error"
    return "invalid_provider_response"


def provider_route_snapshot(provider: dict) -> dict:
    """Return safe runtime route state without URLs, tokens or upstream text."""
    from app.capability_runtime import capability_release_id

    provider_id = _provider_id(provider)
    if provider.get("protocol") == "codex_cli":
        from app.codex_cli_provider import codex_cli_configuration

        configured = bool(provider.get("routable", True) and codex_cli_configuration().get("configured"))
    elif provider.get("protocol") == "home_factory":
        from app.home_factory_response import factory_response_configuration

        configured = bool(
            provider.get("routable", True)
            and factory_response_configuration().get("configured")
        )
    else:
        configured = bool(
            provider.get("routable", True)
            and provider.get("credential_source") == "server_env"
            and provider.get("key")
            and provider.get("model")
            and provider.get("url")
        )
    raw_state = _provider_route_state.get(provider_id, {})
    state = raw_state if raw_state.get("release_id") == capability_release_id() else {}
    circuit_open = not _provider_is_healthy(provider)
    if not configured:
        status = "unavailable"
    elif circuit_open:
        status = "blocked"
    elif state.get("status") == "live":
        status = "live"
    else:
        status = "unverified"
    return {
        "id": provider_id,
        "model": str(provider.get("model") or ""),
        "configured": configured,
        "routable": configured and not circuit_open,
        "status": status,
        "verified_at": state.get("verified_at"),
        "failure_kind": state.get("failure_kind") if circuit_open else None,
        "credential_source": str(provider.get("credential_source") or "none"),
    }


def provider_failure_event(provider: dict, error: Exception, *, will_retry: bool) -> dict:
    """Build a sanitized durable-style fallback event for the public stream."""
    return {
        "content": "",
        "done": False,
        "provider_event": {
            "type": "provider.attempt.failed",
            "provider": _provider_id(provider),
            "model": str(provider.get("model") or ""),
            "failure_kind": _safe_failure_kind(error),
            "will_retry": will_retry,
        },
    }


def work_summary_event(
    stage: str,
    summary: str,
    *,
    status: str,
    provider: str | None = None,
    model: str | None = None,
    artifact_type: str | None = None,
    artifact_id: str | None = None,
) -> dict:
    """Build a safe public execution-stage event.

    Only observable lifecycle facts belong here.  Provider prompts, hidden
    reasoning and unverified claims are intentionally not part of the schema.
    """
    work_summary = {
        "stage": stage,
        "summary": summary,
        "status": status,
    }
    # ``provider`` and ``model`` remain accepted for internal call-site
    # compatibility, but are intentionally absent from the public trace.
    # Provenance belongs to the protected control surface.
    _ = provider, model
    optional = {
        "artifact_type": artifact_type,
        "artifact_id": artifact_id,
    }
    work_summary.update({key: value for key, value in optional.items() if value})
    return {"content": "", "done": False, "work_summary": work_summary}


def _select_provider(task_type: str = "chat") -> dict:
    """Auto-select best provider based on speed test results.
    
    Speed ranking (tested):
    1. kimi_code     — 1.7 сек (самый быстрый)
    2. kimi_fast     — 1.8 сек (быстрый, дороже)
    3. deepseek_pro  — 2.3 сек (лучший баланс)
    4. mimo          — 3.3 сек (бесплатный)
    5. deepseek_flash— 3.5 сек (бюджетный)
    6. cfbt          — 3.9 сек (бесплатный,
    "codex_result": {
        "id": "codex_result",
        "url": os.getenv("CODEX_RESULT_BASE_URL", "http://127.0.0.1:8000") + "/codex/result",
        "model": os.getenv("CODEX_RESULT_MODEL", "codex-result-v1"),
        "key": os.getenv("CODEX_RESULT_API_KEY", ""),
        "credential_source": "server_env",
        "routable": True,
        "cost": "low",
        "speed_ms": 0,
        "speed": "adaptive",
        "quality": "best",
    }
)
    """
    def _available(name: str) -> bool:
        p = PROVIDERS.get(name)
        if not p:
            return False
        return _provider_is_configured(name, p) and _provider_is_healthy(p)

    # Production responses are fail-closed through the one Home task
    # authority.  A Control Plane incident must not silently turn the web
    # backend into a second, unfenced provider scheduler.
    if os.getenv("KOLIBRI_FACTORY_RESPONSES_ENABLED", "").lower() in {
        "1", "true", "yes", "on",
    }:
        if _available("codex_cli") and PROVIDERS["codex_cli"].get("protocol") == "home_factory":
            return PROVIDERS["codex_cli"]
        raise RuntimeError("home_factory_route_unavailable")

    # Speed-critical tasks → fastest available
    if task_type == "fast":
        for name in ("codex_cli", "mimo", "deepseek_flash", "kimi_code", "cfbt"):
            if _available(name):
                return PROVIDERS[name]

    # Complex analysis → best quality + speed balance
    if task_type in ("analyze", "generate", "code"):
        for name in ("codex_cli", "mimo", "deepseek_pro", "deepseek_flash", "kimi_code", "cfbt"):
            if _available(name):
                return PROVIDERS[name]

    # Simple chat → cheapest fast option
    if task_type in ("chat", "suggest"):
        for name in ("codex_cli", "mimo", "deepseek_flash", "deepseek_pro", "kimi_code", "cfbt"):
            if _available(name):
                return PROVIDERS[name]

    # Default → fastest available
    for name in ("codex_cli", "mimo", "deepseek_pro", "deepseek_flash", "kimi_code", "cfbt"):
        if _available(name):
            return PROVIDERS[name]

    raise RuntimeError("provider_routes_exhausted")


async def chat_completion(
    messages: List[Dict[str, str]],
    task_type: str = "chat",
    system: Optional[str] = None,
    raw_json_output: bool = False,
    previous_response_id: Optional[str] = None,
    background: bool = False,
    policy: Optional[dict] = None,
    idempotency_key: Optional[str] = None,
) -> dict:
    """Call AI with auto-routing and fallback."""
    # Structured-output transports own their exact JSON contract.  Intent
    # helpers (image routing, self-description and estimate materialisation)
    # must not replace or rewrite the provider JSON before schema validation.
    image_result = (
        None
        if raw_json_output
        else await _image_completion_if_requested(messages, policy)
    )
    if image_result is not None:
        return image_result
    if not raw_json_output and system is None and _is_self_description_request(messages):
        return _capability_self_description()
    full_messages = [{"role": "system", "content": _compose_system_prompt(system)}] + messages
    
    # Get ordered list of providers to try
    providers_to_try = _get_providers_for_task(task_type)
    
    provider_attempts: list[dict] = []
    for provider in providers_to_try:
        try:
            if previous_response_id or background or policy is not None or idempotency_key:
                result = await _call_ai(
                    provider,
                    full_messages,
                    previous_response_id=previous_response_id,
                    background=background,
                    policy=policy,
                    idempotency_key=idempotency_key,
                )
            else:
                result = await _call_ai(provider, full_messages)
            _record_provider_success(provider)
            result["actions"] = (
                []
                if raw_json_output
                else await _materialize_estimate_actions(
                    messages, result.get("actions", [])
                )
            )
            if result["actions"]:
                result["status"] = "ready"
            if not raw_json_output and is_estimate_request(messages) and result["actions"]:
                # Provider JSON is an internal typed draft.  Never expose the
                # raw fenced object next to the materialised estimate editor.
                result["content"] = _estimate_result_message(result["actions"])
                result["reasoning"] = ""
            result["fallback_used"] = len(providers_to_try) > 1 and provider != providers_to_try[0]
            result["provider_attempts"] = provider_attempts + [{
                "provider": _provider_id(provider),
                "model": str(provider.get("model") or ""),
                "status": "completed",
            }]
            return result
        except Exception as e:
            _record_provider_failure(provider, e)
            provider_attempts.append({
                "provider": _provider_id(provider),
                "model": str(provider.get("model") or ""),
                "status": "failed",
                "failure_kind": _safe_failure_kind(e),
            })
            print(
                f"[AI FALLBACK] provider={_provider_id(provider)} "
                f"failure={_safe_failure_kind(e)} trying_next=true"
            )
            continue
    
    # All providers failed
    local_actions = (
        []
        if raw_json_output
        else await _materialize_estimate_actions(messages, [])
    )
    return {
        "content": _estimate_result_message(local_actions) if local_actions else (
            "Не удалось завершить ответ через доступные маршруты. Повторите запрос — он будет направлен другому исполнителю."
        ),
        "reasoning": "",
        "actions": local_actions,
        "status": "ready" if local_actions else "error",
        "provider": "local_contract" if local_actions else "none",
        "model": "deterministic-estimate-v1" if local_actions else "none",
        "speed_ms": 0,
        "fallback_used": True,
        "provider_attempts": provider_attempts,
        "error_code": "provider_routes_exhausted",
    }


def _get_providers_for_task(task_type: str) -> list:
    """Get ordered list of providers to try for a task type."""
    def _available(name: str) -> bool:
        p = PROVIDERS.get(name)
        if not p:
            return False
        return _provider_is_configured(name, p) and _provider_is_healthy(p)

    if os.getenv("KOLIBRI_FACTORY_RESPONSES_ENABLED", "").lower() in {
        "1", "true", "yes", "on",
    }:
        provider = PROVIDERS["codex_cli"]
        return [provider] if provider.get("protocol") == "home_factory" and _available("codex_cli") else []
    
    if task_type == "fast":
        order = ("codex_cli", "mimo", "deepseek_flash", "deepseek_pro", "kimi_code", "kimi_fast", "cfbt")
    elif task_type in ("analyze", "generate", "code"):
        order = ("codex_cli", "mimo", "deepseek_pro", "deepseek_flash", "kimi_code", "cfbt")
    elif task_type in ("chat", "suggest"):
        order = ("codex_cli", "mimo", "deepseek_flash", "deepseek_pro", "kimi_code", "cfbt")
    else:
        order = ("codex_cli", "mimo", "deepseek_pro", "deepseek_flash", "kimi_code", "cfbt")
    
    return [PROVIDERS[name] for name in order if _available(name)]


def _estimate_source_collection_enabled() -> bool:
    return os.getenv("KOLIBRI_ESTIMATE_FGIS_ENABLED", "true").lower() in {
        "1", "true", "yes", "on",
    }


async def _materialize_estimate_actions(
    messages: List[Dict[str, str]],
    actions: list[dict],
) -> list[dict]:
    """Cross the estimate price trust boundary through official evidence only."""

    normalized = ensure_estimate_action(messages, actions)
    estimate = next((item for item in normalized if item.get("type") == "create_estimate"), None)
    if estimate is None:
        return normalized

    draft = deepcopy(estimate.get("data") or {})
    # Provider prices are scope suggestions, not price evidence.  Zero them
    # before research so an unmatched row cannot silently retain an invented
    # amount in the editor or totals.
    for section in draft.get("sections", []):
        if not isinstance(section, dict):
            continue
        for position in section.get("positions", []):
            if not isinstance(position, dict):
                continue
            position["price"] = "0.00"
            position["sum"] = "0.00"
            position["source"] = ""
            position["price_evidence"] = []

    trusted_evidence: list[dict] = []
    if _estimate_source_collection_enabled():
        try:
            from app.fgiscs_client import FgisCsClient

            draft, trusted_evidence = await FgisCsClient().enrich_draft(draft)
        except Exception:
            # Price research is an optional, untrusted boundary.  Transport,
            # payload and local attestation/configuration failures must all
            # degrade to zero unverified prices instead of aborting the chat or
            # its SSE stream.  asyncio cancellation remains a BaseException and
            # is therefore not swallowed here.
            trusted_evidence = []

    final_estimate = build_estimate_action(
        latest_user_text(messages),
        draft,
        verified_evidence=trusted_evidence,
        scope_verified=False,
    )
    # The collector assigns a price before the shared evidence contract makes
    # its final freshness/region/unit/attestation decision.  If that decision
    # rejects a record, do not leave the now-unbound amount in totals under a
    # softer "preliminary" label: zero it and derive the action again.
    sanitized = deepcopy(final_estimate["data"])
    removed_rejected_price = False
    for section in sanitized.get("sections", []):
        for position in section.get("positions", []):
            if position.get("price_evidence"):
                continue
            if str(position.get("price") or "0") not in {"0", "0.0", "0.00"}:
                removed_rejected_price = True
            position["price"] = "0.00"
            position["sum"] = "0.00"
            position["source"] = ""
    if removed_rejected_price:
        final_estimate = build_estimate_action(
            latest_user_text(messages),
            sanitized,
            verified_evidence=trusted_evidence,
            scope_verified=False,
        )
    return [
        final_estimate if item is estimate else item
        for item in normalized
    ]


def _estimate_result_message(actions: list[dict]) -> str:
    estimate = next((item for item in actions if item.get("type") == "create_estimate"), None)
    status = str((estimate or {}).get("data", {}).get("estimate_status") or "needs_input")
    if status == "verified":
        return "Проверенная смета рассчитана и подготовлена для сохранения в редакторе."
    if status == "source_backed":
        return (
            "Индивидуальная смета рассчитана по последним опубликованным региональным "
            "ценам ФГИС ЦС и подготовлена для редактора. Объёмы требуют проверки по проекту."
        )
    if status == "preliminary":
        return (
            "Индивидуальная ведомость сформирована, но не все строки имеют подходящий "
            "актуальный региональный источник. Неподтверждённые цены не включены."
        )
    return (
        "Готовой сметы пока нет: исполнитель не сформировал достаточный индивидуальный "
        "состав либо не найдены подтверждённые цены. Откройте результат и уточните исходные данные."
    )


async def analyze_estimate(estimate_data: dict) -> dict:
    """AI analysis of an estimate."""
    prompt = f"""Проанализируй смету и дай рекомендации:
- Названия: {estimate_data.get('title', '')}
- Клиент: {estimate_data.get('client', '')}
- Итого: {estimate_data.get('total', '0')} ₽
- Разделы: {len(estimate_data.get('sections', []))}

Позиции:
"""
    for s in estimate_data.get("sections", []):
        prompt += f"\n{s.get('title', '')}:\n"
        for p in s.get("positions", []):
            prompt += f"  - {p.get('name', '')}: {p.get('quantity', '0')} {p.get('unit', '')} × {p.get('price', '0')} ₽ = {p.get('sum', '0')} ₽\n"

    prompt += "\nДай краткий анализ: корректность расчётов, возможные ошибки, рекомендации по оптимизации."
    return await chat_completion(
        [{"role": "user", "content": prompt}],
        task_type="analyze",
        system="Ты — эксперт по строительным сметам. Анализируй данные, находи ошибки, предлагай оптимизации.",
    )


async def generate_document_content(doc_type: str, context: str = "") -> dict:
    """AI generation of document content."""
    type_labels = {
        "contract": "договор подряда", "act": "акт выполненных работ",
        "proposal": "коммерческое предложение", "report": "технический отчёт",
        "memo": "служебная записка", "letter": "деловое письмо",
    }
    label = type_labels.get(doc_type, "документ")
    prompt = f"Составь шаблон: {label}."
    if context:
        prompt += f"\nКонтекст: {context}"
    prompt += "\nВерни готовый HTML-текст с заголовками и параграфами."
    return await chat_completion(
        [{"role": "user", "content": prompt}],
        task_type="generate",
        system="Ты — юридический ассистент. Составляй документы по российским стандартам.",
    )


async def suggest_search(query: str) -> dict:
    """AI search suggestions."""
    prompt = f"Пользователь ищет: '{query}'. Предложи 3-5 релевантных запросов."
    return await chat_completion(
        [{"role": "user", "content": prompt}],
        task_type="suggest",
        system="Ты — поисковый ассистент. Предлагай релевантные запросы.",
    )


async def _call_ai(
    provider: dict,
    messages: List[Dict[str, str]],
    system: Optional[str] = None,
    *,
    previous_response_id: Optional[str] = None,
    background: bool = False,
    policy: Optional[dict] = None,
    idempotency_key: Optional[str] = None,
) -> dict:
    """Internal: call AI API."""
    full = []
    if system:
        full.append({"role": "system", "content": system})
    full.extend(messages)

    if provider.get("protocol") == "home_factory":
        from app.home_factory_response import get_home_factory_response_client

        parsed = await get_home_factory_response_client().submit(
            full,
            idempotency_key=idempotency_key,
        )
        content = str(parsed.get("content") or "")
        if not content.strip():
            raise ValueError("provider_returned_empty_content")
        actions = _extract_actions(content)
        return {
            "content": content,
            "reasoning": "",
            "actions": actions,
            "status": "ready" if actions else "idle",
            "provider": "home_factory",
            "model": str(parsed.get("model") or "kolibri"),
            "speed_ms": provider.get("speed_ms", 0),
            "tool_events": parsed.get("tool_events", []),
            "factory": {
                key: parsed.get(key)
                for key in (
                    "task_id",
                    "attempt_id",
                    "fencing_token",
                    "executor_node",
                    "verifier_node",
                    "artifact_sha256",
                    "binding_sha256",
                    "result_reference",
                )
            },
        }

    if provider.get("protocol") == "codex_cli":
        from app.codex_cli_provider import get_codex_cli_provider

        parsed = await get_codex_cli_provider().invoke(
            full,
            policy=policy,
        )
        content = str(parsed.get("content") or "")
        if not content.strip():
            raise ValueError("provider_returned_empty_content")
        actions = _extract_actions(content)
        return {
            "content": content,
            "reasoning": "",
            "actions": actions,
            "status": "ready" if actions else "idle",
            "provider": _provider_id(provider),
            "model": str(parsed.get("model") or provider["model"]),
            "speed_ms": provider.get("speed_ms", 0),
            "tool_events": parsed.get("tool_events", []),
        }

    if provider.get("protocol") == "responses":
        from app.openai_responses import create_response

        parsed = await create_response(
            provider,
            full,
            previous_response_id=previous_response_id,
            background=background,
            policy=policy,
            idempotency_key=idempotency_key,
        )
        content = str(parsed.get("content") or "")
        effective_background = background or bool(
            policy and policy.get("mode") == "deep" and policy.get("background")
        )
        if effective_background and parsed.get("status") in {"queued", "in_progress"}:
            return {
                "content": "",
                "reasoning": "",
                "actions": [],
                "status": str(parsed.get("status")),
                "provider": _provider_id(provider),
                "model": provider["model"],
                "speed_ms": provider.get("speed_ms", 0),
                "response_id": parsed.get("id"),
                "tool_events": parsed.get("tool_events", []),
            }
        if not content.strip():
            raise ValueError("provider_returned_empty_content")
        return {
            "content": content,
            "reasoning": str(parsed.get("reasoning_summary") or ""),
            "actions": _extract_actions(content),
            "status": "ready" if _extract_actions(content) else "idle",
            "provider": _provider_id(provider),
            "model": provider["model"],
            "speed_ms": provider.get("speed_ms", 0),
            "response_id": parsed.get("id"),
            "tool_events": parsed.get("tool_events", []),
        }

    headers = {"Content-Type": "application/json"}
    if provider["key"]:
        headers["Authorization"] = f"Bearer {provider['key']}"

    async with httpx.AsyncClient(timeout=AI_TIMEOUT) as client:
        response = await client.post(
            provider["url"],
            json={"model": provider["model"], "messages": full},
            headers=headers,
        )
        response.raise_for_status()
        data = response.json()

    msg = data["choices"][0]["message"]
    content = msg.get("content") or ""
    reasoning = msg.get("reasoning_content") or ""
    if not content.strip():
        raise ValueError("provider_returned_empty_content")
    actions = _extract_actions(content)

    return {
        "content": content,
        "reasoning": reasoning,
        "actions": actions,
        "status": "ready" if actions else "idle",
        "provider": _provider_id(provider),
        "model": provider["model"],
        "speed_ms": provider.get("speed_ms", 0),
    }


async def chat_completion_stream(
    messages: List[Dict[str, str]],
    task_type: str = "chat",
    *,
    system: Optional[str] = None,
    raw_json_output: bool = False,
    previous_response_id: Optional[str] = None,
    background: bool = False,
    policy: Optional[dict] = None,
    idempotency_key: Optional[str] = None,
    run_id: Optional[str] = None,
):
    """Yield token deltas followed by one structured, reasoning-free final chunk.

    Provider streams are deliberately normalised here instead of being passed
    through verbatim.  Besides keeping the public stream stable across
    OpenAI-compatible providers, this prevents provider-specific private
    reasoning fields from leaking into the client response.
    """
    image_result = await _image_completion_if_requested(messages, policy, run_id=run_id)
    if image_result is not None:
        if image_result["status"] == "ready":
            yield work_summary_event("tool_execution", "Создаю изображение", status="active")
            yield work_summary_event(
                "artifact_verification",
                "Формат, размер и контрольная сумма изображения проверены",
                status="completed",
                provider=image_result["provider"],
                model=image_result["model"],
                artifact_type="image",
                artifact_id=image_result["actions"][0]["data"]["id"],
            )
        yield {
            "content": image_result["content"],
            "done": True,
            "actions": image_result["actions"],
            "status": image_result["status"],
            "provider": image_result["provider"],
            "model": image_result["model"],
            "fallback_used": False,
            **({
                "error_code": image_result["error_code"],
                "recoverable": image_result["recoverable"],
                "capability": image_result["capability"],
            } if image_result.get("error_code") else {}),
        }
        return
    if system is None and _is_self_description_request(messages):
        result = _capability_self_description()
        yield {"content": result["content"], "done": False}
        yield {
            "content": "",
            "done": True,
            "actions": [],
            "status": "idle",
            "provider": result["provider"],
            "model": result["model"],
            "fallback_used": False,
        }
        return
    full_messages = [{"role": "system", "content": _compose_system_prompt(system)}] + messages
    providers_to_try = _get_providers_for_task(task_type)
    estimate_requested = is_estimate_request(messages)

    for provider_index, provider in enumerate(providers_to_try):
        provider_id = _provider_id(provider)
        provider_model = str(provider.get("model") or "")
        yield work_summary_event(
            "provider_route",
            "Подключаю доступного исполнителя",
            status="active",
            provider=provider_id,
            model=provider_model,
        )
        emitted_content = False
        content_parts: list[str] = []
        structured_output = False
        visible_buffer = ""
        response_meta: dict = {}
        try:
            stream_kwargs: dict[str, object] = {}
            if previous_response_id:
                stream_kwargs["previous_response_id"] = previous_response_id
            if background:
                stream_kwargs["background"] = background
            if policy is not None:
                stream_kwargs["policy"] = policy
            if idempotency_key:
                stream_kwargs["idempotency_key"] = idempotency_key
            # Correlation is supported only by the bounded local CLI and Home
            # factory transports; never smuggle it into external REST payloads.
            if (
                provider.get("protocol") in {"codex_cli", "home_factory"}
                and run_id
            ):
                stream_kwargs["run_id"] = run_id
            stream = (
                _stream_ai(provider, full_messages, **stream_kwargs)
                if stream_kwargs
                else _stream_ai(provider, full_messages)
            )
            async for chunk in stream:
                if chunk.get("work_summary") or chunk.get("tool_event"):
                    yield chunk
                    continue
                if chunk.get("response_meta"):
                    response_meta.update(chunk["response_meta"])
                    continue
                token = chunk.get("content") or ""
                if not token:
                    # The upstream [DONE] marker is replaced with the
                    # structured final event emitted below.
                    continue
                emitted_content = True
                content_parts.append(token)
                if raw_json_output:
                    yield {"content": token, "done": False}
                    continue
                if structured_output:
                    continue

                visible_buffer += token
                stripped = visible_buffer.lstrip()
                fence_index = visible_buffer.lower().find("```json")
                if stripped.startswith("{"):
                    structured_output = True
                    visible_buffer = ""
                elif fence_index >= 0:
                    prefix = visible_buffer[:fence_index]
                    if prefix:
                        yield {"content": prefix, "done": False}
                    structured_output = True
                    visible_buffer = ""
                elif len(visible_buffer) > 7:
                    safe_prefix = visible_buffer[:-7]
                    visible_buffer = visible_buffer[-7:]
                    if safe_prefix:
                        yield {"content": safe_prefix, "done": False}

            effective_background = background or bool(
                policy and policy.get("mode") == "deep" and policy.get("background")
            )
            if (
                not emitted_content
                and effective_background
                and response_meta.get("status") in {"queued", "in_progress"}
            ):
                _record_provider_success(provider)
                yield {
                    "content": "",
                    "done": True,
                    "actions": [],
                    "status": response_meta["status"],
                    "provider": provider_id,
                    "model": provider_model,
                    "fallback_used": provider_index > 0,
                    "response_id": response_meta.get("id"),
                }
                return
            if not emitted_content:
                raise ValueError("provider_returned_empty_content")

            _record_provider_success(provider)
            yield work_summary_event(
                "response_received",
                "Ответ исполнителя получен",
                status="completed",
                provider=provider_id,
                model=provider_model,
            )
            actions = [] if raw_json_output else await _materialize_estimate_actions(
                messages, _extract_actions("".join(content_parts))
            )
            if structured_output and actions:
                action_type = actions[0].get("type")
                summary = {
                    "create_estimate": _estimate_result_message(actions),
                    "create_document": "Документ подготовлен для сохранения в текущем проекте.",
                }.get(action_type, "Результат подготовлен для сохранения в текущем проекте.")
                yield {
                    "content": summary,
                    "done": False,
                }
            elif visible_buffer:
                yield {"content": visible_buffer, "done": False}
            final = {
                "content": "",
                "done": True,
                "actions": actions,
                "status": "ready" if actions else "idle",
                "provider": _provider_id(provider),
                "model": provider.get("model", ""),
                "fallback_used": provider_index > 0,
            }
            if response_meta.get("id"):
                final["response_id"] = response_meta["id"]
            yield final
            return
        except Exception as e:
            if _safe_failure_kind(e) == "codex_cli_cancelled":
                yield {
                    "content": "",
                    "done": True,
                    "actions": [],
                    "status": "cancelled",
                    "provider": provider_id,
                    "model": provider_model,
                    "fallback_used": provider_index > 0,
                }
                return
            _record_provider_failure(provider, e)
            yield provider_failure_event(
                provider,
                e,
                will_retry=not emitted_content and provider_index < len(providers_to_try) - 1,
            )
            print(
                f"[AI STREAM FALLBACK] provider={_provider_id(provider)} "
                f"failure={_safe_failure_kind(e)} trying_next={not emitted_content}"
            )
            if emitted_content:
                yield {
                    "content": "",
                    "done": True,
                    "actions": await _materialize_estimate_actions(
                        messages, _extract_actions("".join(content_parts))
                    ),
                    "status": "ready" if estimate_requested else "incomplete",
                    "provider": _provider_id(provider),
                    "model": provider.get("model", ""),
                    "fallback_used": provider_index > 0,
                    "error_code": "provider_stream_interrupted",
                }
                return
            continue

    local_actions = await _materialize_estimate_actions(messages, [])
    if local_actions:
        yield work_summary_event(
            "response_received",
            "Подготовлен локальный детерминированный результат",
            status="completed",
            provider="local_contract",
            model="deterministic-estimate-v1",
        )
    yield {
        "content": _estimate_result_message(local_actions) if local_actions else (
            "Не удалось завершить ответ через доступные маршруты. Повторите запрос — он будет направлен другому исполнителю."
        ),
        "done": True,
        "actions": local_actions,
        "status": "ready" if local_actions else "error",
        "provider": "local_contract" if local_actions else "none",
        "model": "deterministic-estimate-v1" if local_actions else "none",
        "fallback_used": bool(providers_to_try),
        "error_code": "provider_routes_exhausted",
    }


async def _stream_ai(
    provider: dict,
    messages: List[Dict[str, str]],
    system: Optional[str] = None,
    *,
    previous_response_id: Optional[str] = None,
    background: bool = False,
    policy: Optional[dict] = None,
    idempotency_key: Optional[str] = None,
    run_id: Optional[str] = None,
):
    """Internal: stream tokens from AI API using httpx async streaming."""
    full = []
    if system:
        full.append({"role": "system", "content": system})
    full.extend(messages)

    if provider.get("protocol") == "home_factory":
        from app.home_factory_response import get_home_factory_response_client

        async for event in get_home_factory_response_client().stream(
            full,
            run_id=run_id,
            idempotency_key=idempotency_key,
        ):
            yield event
        return

    if provider.get("protocol") == "codex_cli":
        from app.codex_cli_provider import get_codex_cli_provider

        async for event in get_codex_cli_provider().stream(
            full,
            policy=policy,
            run_id=run_id,
        ):
            yield event
        return

    if provider.get("protocol") == "responses":
        from app.openai_responses import stream_response

        async for event in stream_response(
            provider,
            full,
            previous_response_id=previous_response_id,
            background=background,
            policy=policy,
            idempotency_key=idempotency_key,
        ):
            yield event
        return

    headers = {"Content-Type": "application/json"}
    if provider["key"]:
        headers["Authorization"] = f"Bearer {provider['key']}"

    async with httpx.AsyncClient(timeout=httpx.Timeout(AI_TIMEOUT, connect=10.0)) as client:
        async with client.stream(
            "POST",
            provider["url"],
            json={"model": provider["model"], "messages": full, "stream": True},
            headers=headers,
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    yield {"content": "", "done": True}
                    return
                try:
                    obj = json.loads(data_str)
                    delta = obj["choices"][0].get("delta", {})
                    token = delta.get("content") or ""
                    if token:
                        yield {"content": token, "done": False}
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue


def _extract_actions(content: str) -> list:
    """Extract fenced, raw or prose-embedded JSON actions safely."""
    actions: list[dict] = []
    objects: list[dict] = []
    seen: set[str] = set()

    candidates = [part.split("```")[0].strip() for part in content.split("```json")[1:]]
    decoder = json.JSONDecoder()
    for index, character in enumerate(content):
        if character != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(content[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            candidates.append(json.dumps(obj, ensure_ascii=False, sort_keys=True))

    for json_str in candidates:
        try:
            obj = json.loads(json_str)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        fingerprint = json.dumps(obj, ensure_ascii=False, sort_keys=True)
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        objects.append(obj)

    for obj in objects:
        action_type = obj.get("action", "")
        if action_type == "create_estimate":
            candidate = dict(obj)
            candidate.pop("action", None)
            actions.append(build_estimate_action("", candidate))
        elif action_type == "create_document":
            document_text = str(obj.get("content") or "").strip()
            paragraphs = [part.strip() for part in document_text.splitlines() if part.strip()]
            safe_content = "".join(f"<p>{escape(part)}</p>" for part in paragraphs)
            actions.append({
                "type": "create_document",
                "label": f"Создать {obj.get('title', 'документ')}",
                "data": {
                    "title": obj.get("title", "Документ"),
                    "type": obj.get("type", "custom"),
                    "content": safe_content,
                },
            })
    return actions
