import re
import json as _json
import httpx
from logging_config import get_logger

logger = get_logger("providers")

from config import AI_API_KEY, AI_BASE_URL, AI_MODEL, FORMULALM_URL, FORMULALM_ENABLED

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


class FormulaLMProvider:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    async def generate(self, prompt: str, max_tokens: int = 256, temperature: float = 0.7) -> dict:
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{self.base_url}/api/v1/generate",
                    json={
                        "prompt": prompt,
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                return {
                    "response": data.get("text", ""),
                    "provider": "formulalm",
                    "model": "formulalm",
                    "tokens_generated": data.get("tokens_generated", 0),
                }
        except httpx.ConnectError:
            logger.warning("FormulaLM engine unreachable at %s", self.base_url)
            return None
        except Exception as e:
            logger.error("FormulaLM generate error: %s", e, exc_info=True)
            return None

    async def generate_stream(self, prompt: str, max_tokens: int = 256, temperature: float = 0.7):
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/api/v1/generate/stream",
                    json={
                        "prompt": prompt,
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                    },
                ) as resp:
                    resp.raise_for_status()
                    buffer = ""
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        payload = line[6:]
                        if payload.strip() == "[DONE]":
                            break
                        try:
                            chunk = _json.loads(payload)
                            text = chunk.get("text", "")
                            if text:
                                buffer += text
                                yield {"chunk": text, "provider": "formulalm", "model": "formulalm"}
                        except Exception:
                            continue
                    yield {"done": True, "response": buffer.strip(), "provider": "formulalm", "model": "formulalm"}
        except httpx.ConnectError:
            logger.warning("FormulaLM stream unreachable at %s", self.base_url)
            yield {"chunk": "", "provider": "formulalm", "model": "formulalm", "done": True, "response": ""}
        except Exception as e:
            logger.error("FormulaLM stream error: %s", e, exc_info=True)
            yield {"chunk": f"Error: {e}", "provider": "error", "model": "none", "done": True, "response": ""}

    async def is_available(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.base_url}/api/v1/health")
                return resp.status_code == 200
        except Exception:
            return False


class AIProviderManager:
    def __init__(self):
        self.api_key = AI_API_KEY
        self.base_url = AI_BASE_URL.rstrip("/")
        self.model = AI_MODEL
        self.formulalm = FormulaLMProvider(FORMULALM_URL) if FORMULALM_ENABLED else None

    def get_status(self):
        statuses = [
            {"name": "mimo", "available": bool(self.api_key), "status": "online" if self.api_key else "offline"},
            {"name": "openai", "available": False, "status": "offline"},
            {"name": "anthropic", "available": False, "status": "offline"},
        ]
        if self.formulalm:
            statuses.append({"name": "formulalm", "available": True, "status": "online"})
        else:
            statuses.append({"name": "formulalm", "available": False, "status": "offline"})
        return statuses

    def get_model_catalog(self):
        models = [
            {"name": "mimo-v2.5-pro", "description": "High quality reasoning", "available": True},
            {"name": "mimo-v2.5-lite", "description": "Fast lightweight model", "available": True},
        ]
        if self.formulalm:
            models.append({"name": "formulalm", "description": "Kolibri evolutionary model (local, CPU-only)", "available": True})
        return models

    def get_system_prompt(self):
        return KOLIBRI_SYSTEM_PROMPT

    async def generate(self, messages, model="auto", provider=None, **kwargs):
        user_text = messages[-1]["content"] if messages else ""
        estimate_mode = is_estimate_intent(user_text)
        system_prompt = ESTIMATE_SYSTEM_PROMPT if estimate_mode else KOLIBRI_SYSTEM_PROMPT
        max_tokens = kwargs.get("max_tokens") or (16384 if estimate_mode else 2048)
        chosen_model = ("mimo-v2.5" if estimate_mode else self.model) if model == "auto" else model

        if chosen_model == "formulalm" or provider == "formulalm":
            if not self.formulalm:
                return {"response": "FormulaLM not enabled. Set KOLIBRI_FORMULALM_ENABLED=true", "provider": "error", "model": "none"}
            prompt = self._messages_to_prompt(messages, system_prompt)
            result = await self.formulalm.generate(
                prompt=prompt,
                max_tokens=min(max_tokens, 512),
                temperature=kwargs.get("temperature", 0.7),
            )
            if result:
                return result
            return {"response": "FormulaLM engine unavailable", "provider": "error", "model": "none"}

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

        if chosen_model == "formulalm" or provider == "formulalm":
            if not self.formulalm:
                yield {"chunk": "FormulaLM not enabled", "provider": "error", "model": "none", "done": True, "response": ""}
                return
            prompt = self._messages_to_prompt(messages, system_prompt)
            async for chunk in self.formulalm.generate_stream(
                prompt=prompt,
                max_tokens=min(max_tokens, 512),
                temperature=kwargs.get("temperature", 0.7),
            ):
                yield chunk
            return

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

    @staticmethod
    def _messages_to_prompt(messages: list, system_prompt: str = "") -> str:
        parts = []
        if system_prompt:
            parts.append(system_prompt)
        for m in messages:
            if isinstance(m, dict):
                role = m.get("role", "user")
                content = m.get("content", "")
            else:
                role = getattr(m, "role", "user")
                content = getattr(m, "content", "")
            if role == "system":
                continue
            parts.append(f"{role}: {content}")
        parts.append("assistant:")
        return "\n".join(parts)


manager = AIProviderManager()
