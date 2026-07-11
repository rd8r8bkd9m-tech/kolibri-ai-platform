#!/usr/bin/env python3
"""Compatibility client for the single public Kolibri model.

Provider and worker selection are internal Factory concerns.  This module no
longer carries a static node catalog or contacts Mimo/Codex workers directly.
"""

from __future__ import annotations

import json
import os
import urllib.request
import warnings


class KolibriClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self.base_url = (
            base_url
            or os.environ.get("KOLIBRI_API_URL")
            or "https://kolibriai.ru"
        ).rstrip("/")
        self.api_key = api_key if api_key is not None else os.environ.get("KOLIBRI_API_KEY", "")

    def _request(self, path: str, payload: dict | None = None, *, timeout: int = 120) -> dict:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Accept": "application/json"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers=headers,
            method="POST" if payload is not None else "GET",
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def respond(self, prompt: str) -> dict:
        return self._request(
            "/v1/responses",
            {"model": "kolibri", "input": prompt},
        )

    def chat(self, prompt: str) -> str:
        response = self.respond(prompt)
        if isinstance(response.get("output_text"), str):
            return response["output_text"]
        output = response.get("output", [])
        for item in output if isinstance(output, list) else []:
            for content in item.get("content", []) if isinstance(item, dict) else []:
                if isinstance(content, dict) and isinstance(content.get("text"), str):
                    return content["text"]
        raise ValueError("kolibri_response_missing_output_text")

    def health(self) -> dict:
        return self._request("/v1/health", timeout=5)


class MimoClient(KolibriClient):
    """Deprecated name retained without direct-provider semantics."""

    def chat(self, server_or_prompt: str, prompt: str | None = None, model: str = "kolibri") -> str:
        warnings.warn(
            "MimoClient is deprecated; use KolibriClient and public model 'kolibri'",
            DeprecationWarning,
            stacklevel=2,
        )
        if model != "kolibri":
            raise ValueError("public_model_must_be_kolibri")
        if prompt is not None and server_or_prompt not in {"home", "kolibri"}:
            raise ValueError("direct_worker_selection_forbidden")
        return super().chat(prompt if prompt is not None else server_or_prompt)

    def list_agents(self) -> list[dict]:
        return [
            {
                "name": "kolibri",
                "url": self.base_url,
                "provider_hidden": True,
                "key_configured": bool(self.api_key),
            }
        ]


if __name__ == "__main__":
    client = KolibriClient()
    print(json.dumps({"model": "kolibri", "url": client.base_url}, ensure_ascii=False))
