import os
import subprocess
import json

KOLIBRI_SYSTEM_PROMPT = (
    "Ты — Kolibri AI, большая языковая модель. " +
    "Отвечай на языке пользователя. Не используй эмодзи."
)

class AIProviderManager:
    def __init__(self):
        self.mimo_path = "/root/.mimocode/bin/mimo"

    def get_status(self):
        providers = []
        for name in ["mimo", "openai", "anthropic", "local"]:
            providers.append({
                "name": name,
                "available": name == "mimo",
                "status": "online" if name == "mimo" else "offline",
            })
        return providers

    def get_model_catalog(self):
        return [
            {"name": "mimo-auto", "description": "Auto mode (recommended)", "available": True},
            {"name": "mimo-v2.5-pro", "description": "High quality reasoning", "available": True},
            {"name": "mimo-v2.5-lite", "description": "Fast lightweight model", "available": True},
        ]

    def get_system_prompt(self):
        return KOLIBRI_SYSTEM_PROMPT

    async def generate(self, messages, model="auto", provider=None, **kwargs):
        user_msg = messages[-1]["content"] if messages else ""
        prompt = f"{KOLIBRI_SYSTEM_PROMPT}\n\nПользователь: {user_msg}\n\nОтвет:"

        try:
            result = subprocess.run(
                [self.mimo_path, "run", "--dangerously-skip-permissions",
                 "--model", "mimo/mimo-auto", prompt],
                capture_output=True, text=True, timeout=120
            )
            response = result.stdout.strip()
            if not response:
                response = result.stderr.strip()
            return {"response": response, "provider": "mimo", "model": "mimo-auto"}
        except Exception as e:
            return {"response": f"Error: {e}", "provider": "error", "model": "none"}

    async def tool_call(self, message, tools=None):
        return {"error": "Tool calls not implemented"}

manager = AIProviderManager()
