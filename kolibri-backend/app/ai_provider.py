"""AI provider — multi-model auto-routing for Kolibri."""
import os
import json
import httpx
from typing import List, Dict, Optional

AI_TIMEOUT = int(os.getenv("AI_TIMEOUT", "60"))

# Provider configs — ordered by speed (fastest first)
PROVIDERS = {
    "kimi_code": {
        "url": os.getenv("KIMI_BASE_URL", "https://api.moonshot.ai/v1") + "/chat/completions",
        "model": os.getenv("KIMI_MODEL", "kimi-k2.7-code"),
        "key": os.getenv("KIMI_API_KEY", ""),
        "cost": "medium",
        "speed_ms": 1700,
        "speed": "fastest",
        "quality": "best",
    },
    "deepseek_pro": {
        "url": os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com") + "/chat/completions",
        "model": "deepseek-v4-pro",
        "key": os.getenv("DEEPSEEK_API_KEY", ""),
        "cost": "low",
        "speed_ms": 2300,
        "speed": "fast",
        "quality": "best",
    },
    "mimo": {
        "url": os.getenv("MIMO_BASE_URL", "https://token-plan-sgp.xiaomimimo.com/v1") + "/chat/completions",
        "model": os.getenv("MIMO_MODEL", "mimo-v2.5-pro"),
        "key": os.getenv("MIMO_API_KEY", ""),
        "cost": "free",
        "speed_ms": 3300,
        "speed": "medium",
        "quality": "good",
    },
    "deepseek_flash": {
        "url": os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com") + "/chat/completions",
        "model": "deepseek-v4-flash",
        "key": os.getenv("DEEPSEEK_API_KEY", ""),
        "cost": "low",
        "speed_ms": 3500,
        "speed": "medium",
        "quality": "good",
    },
    "cfbt": {
        "url": os.getenv("KIMI_CFBT_BASE_URL", "https://cfbt.ccwu.cc/v1") + "/chat/completions",
        "model": os.getenv("KIMI_CFBT_MODEL", "@cf/moonshotai/kimi-k2.6"),
        "key": os.getenv("KIMI_CFBT_API_KEY", ""),
        "cost": "free",
        "speed_ms": 3900,
        "speed": "slow",
        "quality": "good",
    },
    "kimi_fast": {
        "url": os.getenv("KIMI_BASE_URL", "https://api.moonshot.ai/v1") + "/chat/completions",
        "model": "kimi-k2.7-code-highspeed",
        "key": os.getenv("KIMI_API_KEY", ""),
        "cost": "high",
        "speed_ms": 1800,
        "speed": "fastest",
        "quality": "good",
    },
    "deepseek_local": {
        "url": "http://127.0.0.1:8000/deepseek/chat/completions",
        "model": os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
        "key": "local-proxy",
        "cost": "low",
        "speed_ms": 3500,
        "speed": "medium",
        "quality": "good",
    },
}

SYSTEM_PROMPT = """Ты — Колибри, AI-ассистент для строительной компании.
Ты помогаешь с:
- Сметами: создание, расчёт, проверка позиций
- Документами: договоры, акты, коммерческие предложения
- Аналитикой: отчёты, сравнение данных
- Поиском: ищи информацию в документах, сметах, интернете

Когда пользователь просит создать смету — верни JSON-действие в формате:
```json
{"action": "create_estimate", "title": "...", "sections": [{"title": "...", "positions": [{"code":"...", "name":"...", "unit":"...", "quantity":"...", "price":"..."}]}]}
```

Когда просит создать документ — верни:
```json
{"action": "create_document", "title": "...", "type": "contract|act|proposal|report|memo|letter"}
```

Когда нужна информация из интернета — используй веб-поиск.
Когда ищешь в документах — используй локальный поиск.

Отвечай на русском. Будь краток и практичен."""


def _select_provider(task_type: str = "chat") -> dict:
    """Auto-select best provider based on speed test results.
    
    Speed ranking (tested):
    1. kimi_code     — 1.7 сек (самый быстрый)
    2. kimi_fast     — 1.8 сек (быстрый, дороже)
    3. deepseek_pro  — 2.3 сек (лучший баланс)
    4. mimo          — 3.3 сек (бесплатный)
    5. deepseek_flash— 3.5 сек (бюджетный)
    6. cfbt          — 3.9 сек (бесплатный)
    """
    def _available(name: str) -> bool:
        p = PROVIDERS.get(name)
        if not p:
            return False
        return bool(p["key"]) or name == "cfbt"

    # Speed-critical tasks → fastest available
    if task_type == "fast":
        for name in ("kimi_code", "kimi_fast", "deepseek_pro", "mimo", "cfbt"):
            if _available(name):
                return PROVIDERS[name]

    # Complex analysis → best quality + speed balance
    if task_type in ("analyze", "generate", "code"):
        for name in ("kimi_code", "deepseek_pro", "mimo", "cfbt"):
            if _available(name):
                return PROVIDERS[name]

    # Simple chat → cheapest fast option
    if task_type in ("chat", "suggest"):
        for name in ("mimo", "cfbt", "deepseek_flash", "kimi_code"):
            if _available(name):
                return PROVIDERS[name]

    # Default → fastest available
    for name in ("kimi_code", "deepseek_pro", "mimo", "cfbt"):
        if _available(name):
            return PROVIDERS[name]

    return PROVIDERS["cfbt"]  # ultimate fallback


async def chat_completion(messages: List[Dict[str, str]], task_type: str = "chat") -> dict:
    """Call AI with auto-routing and fallback."""
    full_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages
    
    # Get ordered list of providers to try
    providers_to_try = _get_providers_for_task(task_type)
    
    last_error = None
    for provider in providers_to_try:
        try:
            result = await _call_ai(provider, full_messages)
            result["fallback_used"] = len(providers_to_try) > 1 and provider != providers_to_try[0]
            return result
        except Exception as e:
            last_error = e
            print(f"[AI FALLBACK] {provider['model']} failed: {e}, trying next...")
            continue
    
    # All providers failed
    return {
        "content": f"Все AI-провайдеры недоступны. Последняя ошибка: {last_error}",
        "reasoning": "",
        "actions": [],
        "status": "error",
        "provider": "none",
        "model": "none",
        "speed_ms": 0,
        "fallback_used": True,
    }


def _get_providers_for_task(task_type: str) -> list:
    """Get ordered list of providers to try for a task type."""
    def _available(name: str) -> bool:
        p = PROVIDERS.get(name)
        if not p:
            return False
        return bool(p["key"]) or name == "cfbt"
    
    if task_type == "fast":
        order = ("kimi_code", "kimi_fast", "deepseek_pro", "mimo", "cfbt")
    elif task_type in ("analyze", "generate", "code"):
        order = ("kimi_code", "deepseek_pro", "mimo", "cfbt")
    elif task_type in ("chat", "suggest"):
        order = ("mimo", "cfbt", "deepseek_flash", "kimi_code")
    else:
        order = ("kimi_code", "deepseek_pro", "mimo", "cfbt")
    
    return [PROVIDERS[name] for name in order if _available(name)]


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
    provider = _select_provider("analyze")
    return await _call_ai(provider, [{"role": "user", "content": prompt}],
                          system="Ты — эксперт по строительным сметам. Анализируй данные, находи ошибки, предлагай оптимизации.")


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
    provider = _select_provider("generate")
    return await _call_ai(provider, [{"role": "user", "content": prompt}],
                          system="Ты — юридический ассистент. Составляй документы по российским стандартам.")


async def suggest_search(query: str) -> dict:
    """AI search suggestions."""
    prompt = f"Пользователь ищет: '{query}'. Предложи 3-5 релевантных запросов."
    provider = _select_provider("suggest")
    return await _call_ai(provider, [{"role": "user", "content": prompt}],
                          system="Ты — поисковый ассистент. Предлагай релевантные запросы.")


async def _call_ai(provider: dict, messages: List[Dict[str, str]], system: Optional[str] = None) -> dict:
    """Internal: call AI API."""
    full = []
    if system:
        full.append({"role": "system", "content": system})
    full.extend(messages)

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
    actions = _extract_actions(content)

    return {
        "content": content,
        "reasoning": reasoning,
        "actions": actions,
        "status": "ready" if actions else "idle",
        "provider": provider.get("cost", "unknown"),
        "model": provider["model"],
        "speed_ms": provider.get("speed_ms", 0),
    }


async def chat_completion_stream(messages: List[Dict[str, str]], task_type: str = "chat"):
    """Async generator that yields SSE chunks from the AI provider."""
    full_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages
    providers_to_try = _get_providers_for_task(task_type)

    last_error = None
    for provider in providers_to_try:
        try:
            async for chunk in _stream_ai(provider, full_messages):
                yield chunk
            return
        except Exception as e:
            last_error = e
            print(f"[AI STREAM FALLBACK] {provider['model']} failed: {e}, trying next...")
            continue

    yield {"content": f"Все AI-провайдеры недоступны. Последняя ошибка: {last_error}", "done": True}


async def _stream_ai(provider: dict, messages: List[Dict[str, str]], system: Optional[str] = None):
    """Internal: stream tokens from AI API using httpx async streaming."""
    full = []
    if system:
        full.append({"role": "system", "content": system})
    full.extend(messages)

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
    """Extract JSON actions from AI response."""
    actions = []
    if "```json" in content:
        parts = content.split("```json")
        for part in parts[1:]:
            json_str = part.split("```")[0].strip()
            try:
                obj = json.loads(json_str)
                action_type = obj.get("action", "")
                if action_type == "create_estimate":
                    actions.append({
                        "type": "create_estimate",
                        "label": "Создать смету",
                        "data": {"title": obj.get("title", "Новая смета"), "sections": obj.get("sections", [])},
                    })
                elif action_type == "create_document":
                    actions.append({
                        "type": "create_document",
                        "label": f"Создать {obj.get('title', 'документ')}",
                        "data": {"title": obj.get("title", "Документ"), "type": obj.get("type", "custom")},
                    })
            except (json.JSONDecodeError, KeyError):
                continue
    return actions
