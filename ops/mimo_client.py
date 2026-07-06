#!/usr/bin/env python3
"""Kolibri Mimo Client — единый интерфейс для связи с API-агентами.

Использование:
    from mimo_client import MimoClient
    client = MimoClient()
    result = await client.chat("9fts", "обучи модель")
"""

from __future__ import annotations

import os
import json
import urllib.request
import urllib.error


class MimoClient:
    AGENTS = {
        "home": {"url": "http://192.168.88.210:9101", "key_env": "KOLIBRI_CP_KEY"},
        "main": {"url": "http://10.99.0.2:8000", "key_env": "KOLIBRI_API_KEY"},
        "uiap": {"url": "http://10.99.0.3:8002", "key_env": "KOLIBRI_RAG_KEY"},
        "qjns": {"url": "http://10.99.0.4:8003", "key_env": "KOLIBRI_TOOLS_KEY"},
        "9fts": {"url": "http://10.99.0.5:8001", "key_env": "KOLIBRI_INFERENCE_KEY"},
        "new": {"url": "http://10.99.0.6:8001", "key_env": "KOLIBRI_WORKER_KEY"},
    }

    def __init__(self):
        self.keys = {}
        for name, config in self.AGENTS.items():
            key = os.environ.get(config["key_env"], "")
            if key:
                self.keys[name] = key

    def chat(self, server: str, prompt: str, model: str = "mimo") -> str:
        if server not in self.AGENTS:
            raise ValueError(f"Unknown server: {server}")

        agent = self.AGENTS[server]
        key = self.keys.get(server, "")

        payload = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{agent['url']}/v1/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {key}",
            },
        )

        try:
            resp = urllib.request.urlopen(req, timeout=30)
            result = json.loads(resp.read().decode())
            return result["choices"][0]["message"]["content"]
        except Exception as e:
            return f"Error: {e}"

    def health(self, server: str) -> dict:
        if server not in self.AGENTS:
            return {"error": f"Unknown server: {server}"}

        agent = self.AGENTS[server]
        try:
            resp = urllib.request.urlopen(f"{agent['url']}/v1/health", timeout=5)
            return json.loads(resp.read().decode())
        except Exception as e:
            return {"error": str(e)}

    def list_agents(self) -> list[dict]:
        result = []
        for name, config in self.AGENTS.items():
            result.append({
                "name": name,
                "url": config["url"],
                "key_configured": bool(self.keys.get(name)),
            })
        return result


if __name__ == "__main__":
    client = MimoClient()
    print("Kolibri Mimo Client")
    print("=" * 40)
    for agent in client.list_agents():
        status = "✓" if agent["key_configured"] else "✗"
        print(f"  {status} {agent['name']}: {agent['url']}")
