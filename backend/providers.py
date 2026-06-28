import os
import time
import uuid
import urllib.parse

import httpx

KOLIBRI_SYSTEM_PROMPT = (
    "Ты — Kolibri AI, большая языковая модель. " +
    "Отвечай на языке пользователя. Не используй эмодзи."
)

class AIProviderManager:
    def __init__(self):
        self.control_plane_url = os.getenv("KOLIBRI_FACTORY_CONTROL_URL", "http://10.99.0.2:9101").rstrip("/")
        self.timeout = float(os.getenv("KOLIBRI_AI_PROVIDER_TIMEOUT", "45"))
        self.poll_interval = float(os.getenv("KOLIBRI_AI_PROVIDER_POLL_INTERVAL", "0.5"))

    def get_status(self):
        control_configured = bool(self.control_plane_url)
        providers = []
        for name in ["control-plane", "mimo", "openai", "anthropic", "local"]:
            providers.append({
                "name": name,
                "available": name == "control-plane" and control_configured,
                "status": "online" if name == "control-plane" and control_configured else "offline",
            })
        return providers

    def get_model_catalog(self):
        return [
            {"name": "factory-auto", "description": "Control Plane routing", "available": True},
            {"name": "mimo-auto", "description": "Mimo through Agent Host", "available": True},
            {"name": "openai-image", "description": "Image generation through Agent Host", "available": True},
        ]

    def get_system_prompt(self):
        return KOLIBRI_SYSTEM_PROMPT

    async def generate(self, messages, model="auto", provider=None, **kwargs):
        user_msg = messages[-1]["content"] if messages else ""
        prompt = f"{KOLIBRI_SYSTEM_PROMPT}\n\nПользователь: {user_msg}\n\nОтвет:"

        try:
            task = await self._submit_chat_task(prompt, model=model, provider=provider)
            response = self._extract_response(task)
            return {
                "response": response,
                "provider": "control-plane",
                "model": model if model != "auto" else "factory-auto",
                "task_id": task.get("task_id"),
                "state": task.get("state"),
            }
        except Exception as e:
            return {
                "response": "Сейчас не могу получить ответ от фабрики: Control Plane недоступен или задача не завершилась вовремя.",
                "provider": "control-plane",
                "model": "none",
                "error": str(e),
            }

    async def _submit_chat_task(self, prompt: str, model="auto", provider=None) -> dict:
        task_id = f"BACKEND-CHAT-{int(time.time())}-{uuid.uuid4().hex[:8]}"
        runner = provider if provider not in {None, "auto", "control-plane", "factory"} else "mimo"
        envelope = {
            "task_id": task_id,
            "idempotency_key": f"backend-chat:{task_id}",
            "kind": "orchestrator_chat_response",
            "required_capability": "generic_implementation",
            "max_retries": 1,
            "message": prompt,
            "objective": prompt,
            "runner": runner,
            "source": {
                "kind": "backend-api",
                "accepted_at": time.time(),
                "model": model,
            },
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            created = await client.post(f"{self.control_plane_url}/v1/tasks", json=envelope)
            created.raise_for_status()
            created_task = created.json()
            created_task_id = created_task.get("task_id") or task_id
            quoted_task_id = urllib.parse.quote(created_task_id, safe="")
            deadline = time.time() + self.timeout
            while time.time() < deadline:
                current = await client.get(f"{self.control_plane_url}/v1/tasks/{quoted_task_id}")
                current.raise_for_status()
                task = current.json()
                if task.get("state") == "completed":
                    return task
                if task.get("state") in {"failed", "dead_letter", "cancelled"}:
                    raise RuntimeError(task.get("error") or task.get("error_type") or task.get("state"))
                await self._sleep()
            raise TimeoutError(f"Control Plane task timeout: {created_task_id}")

    async def _sleep(self):
        import asyncio
        await asyncio.sleep(self.poll_interval)

    def _extract_response(self, task: dict) -> str:
        result = task.get("result") or {}
        response = result.get("response") or result.get("partial_response")
        if response:
            return str(response).strip()
        return "Фабрика приняла задачу, но не вернула текстовый ответ."

    async def tool_call(self, message, tools=None):
        return {"error": "Tool calls not implemented"}

manager = AIProviderManager()
