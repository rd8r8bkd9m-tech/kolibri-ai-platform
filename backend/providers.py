import re
import json as _json
import httpx
from logging_config import get_logger

logger = get_logger("providers")

from config import AI_API_KEY, AI_BASE_URL, AI_MODEL

KOLIBRI_SYSTEM_PROMPT = (
    "Ты — Kolibri AI, большая языковая модель. "
    "Отвечай на языке пользователя. Не используй эмодзи."
)

ESTIMATE_SYSTEM_PROMPT = """Создай строительную смету в JSON. Регион: Татарстан, Лениногорск. Цены 2025-2026.
Выводи ТОЛЬКО JSON, без markdown и текста.
Формат (ключи на русском):
{"смета":{"проект":"...","площадь":97,"адрес":"...","разделы":[{"номер":1,"название":"...","работы":[{"наименование":"...","единица":"м2","кол_во":100,"цена":500,"сумма":50000}],"итого_по_разделу":50000}],"итого_к_оплате":500000,"примечания":[]}}
Разделы: земляные работы, фундамент, стены, перекрытия, кровля, полы, отделка, инженерные сети, окна/двери, благоустройство. Минимум 3 позиции на раздел."""

ESTIMATE_KEYWORDS = re.compile(
    r"смет[аыу]|расценк[аиу]|цена на|стоимость\s+(работ|материалов|строительства)|"
    r"построить\s+дом|строительств[оа]\s+(дома|жилого|бани|гаража)|создай\s+смет",
    re.IGNORECASE,
)


def is_estimate_intent(text: str) -> bool:
    return bool(ESTIMATE_KEYWORDS.search(text))


class AIProviderManager:
    def __init__(self):
        self.api_key = AI_API_KEY
        self.base_url = AI_BASE_URL.rstrip("/")
        self.model = AI_MODEL

    def get_status(self):
        return [
            {"name": "mimo", "available": bool(self.api_key), "status": "online" if self.api_key else "offline"},
            {"name": "openai", "available": False, "status": "offline"},
            {"name": "anthropic", "available": False, "status": "offline"},
            {"name": "local", "available": False, "status": "offline"},
        ]

    def get_model_catalog(self):
        return [
            {"name": "mimo-v2.5-pro", "description": "High quality reasoning", "available": True},
            {"name": "mimo-v2.5-lite", "description": "Fast lightweight model", "available": True},
        ]

    def get_system_prompt(self):
        return KOLIBRI_SYSTEM_PROMPT

    async def generate(self, messages, model="auto", provider=None, **kwargs):
        user_text = messages[-1]["content"] if messages else ""
        estimate_mode = is_estimate_intent(user_text)
        system_prompt = ESTIMATE_SYSTEM_PROMPT if estimate_mode else KOLIBRI_SYSTEM_PROMPT
        max_tokens = kwargs.get("max_tokens") or (16384 if estimate_mode else 2048)
        chosen_model = ("mimo-v2.5" if estimate_mode else self.model) if model == "auto" else model

        api_messages = [{"role": "system", "content": system_prompt}]
        for m in messages:
            if isinstance(m, dict):
                api_messages.append(m)
            else:
                api_messages.append({"role": m.get("role", "user"), "content": m.get("content", "")})

        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": chosen_model,
                        "messages": api_messages,
                        "temperature": kwargs.get("temperature", 0.3 if estimate_mode else 0.7),
                        "max_tokens": max_tokens,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                response = data["choices"][0]["message"]["content"]
                return {"response": response, "provider": "mimo", "model": chosen_model}
        except Exception as e:
            logger.error(f"generate error: {e}", exc_info=True)
            return {"response": f"Error: {e}", "provider": "error", "model": "none"}

    async def generate_stream(self, messages, model="auto", provider=None, **kwargs):
        user_text = messages[-1]["content"] if messages else ""
        estimate_mode = is_estimate_intent(user_text)
        system_prompt = ESTIMATE_SYSTEM_PROMPT if estimate_mode else KOLIBRI_SYSTEM_PROMPT
        max_tokens = kwargs.get("max_tokens") or (16384 if estimate_mode else 2048)
        chosen_model = ("mimo-v2.5" if estimate_mode else self.model) if model == "auto" else model

        api_messages = [{"role": "system", "content": system_prompt}]
        for m in messages:
            if isinstance(m, dict):
                api_messages.append(m)
            else:
                api_messages.append({"role": m.get("role", "user"), "content": m.get("content", "")})

        buffer = ""

        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": chosen_model,
                        "messages": api_messages,
                        "temperature": kwargs.get("temperature", 0.3 if estimate_mode else 0.7),
                        "max_tokens": max_tokens,
                        "stream": True,
                    },
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        payload = line[6:]
                        if payload.strip() == "[DONE]":
                            break
                        try:
                            chunk = __import__("json").loads(payload)
                            delta = chunk["choices"][0].get("delta", {})
                            text = delta.get("content", "")
                            if text:
                                buffer += text
                                yield {"chunk": text, "provider": "mimo", "model": chosen_model}
                        except Exception:
                            continue
        except Exception as e:
            logger.error(f"generate_stream error: {e}", exc_info=True)
            yield {"chunk": f"Error: {e}", "provider": "error", "model": "none"}

        yield {"done": True, "response": buffer.strip(), "provider": "mimo", "model": chosen_model}

    async def tool_call(self, message, tools=None):
        return {"error": "Tool calls not implemented"}


manager = AIProviderManager()
