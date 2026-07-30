"""Process-lifetime HTTP client for MiMo Code requests."""

from __future__ import annotations

import threading
from typing import Any

import httpx


class MimoClientRuntime:
    """Reuse TLS connections without retaining tenant credentials."""

    def __init__(self, *, timeout_seconds: float) -> None:
        self._timeout = httpx.Timeout(timeout_seconds, connect=10)
        self._client: httpx.Client | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            if self._client is not None:
                return
            self._client = httpx.Client(
                timeout=self._timeout,
                follow_redirects=False,
                trust_env=False,
                limits=httpx.Limits(
                    max_connections=8,
                    max_keepalive_connections=4,
                    keepalive_expiry=60,
                ),
            )

    def post(
        self,
        url: str,
        *,
        api_key: str,
        payload: dict[str, Any],
    ) -> httpx.Response:
        self.start()
        with self._lock:
            client = self._client
        if client is None:
            raise httpx.RequestError("MiMo client is not available")
        return client.post(
            url,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )

    def stream(
        self,
        url: str,
        *,
        api_key: str,
        payload: dict[str, Any],
    ) -> httpx.Response:
        self.start()
        with self._lock:
            client = self._client
        if client is None:
            raise httpx.RequestError("MiMo client is not available")
        request = client.build_request(
            "POST",
            url,
            headers={
                "Accept": "text/event-stream",
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        return client.send(request, stream=True)

    def close(self) -> None:
        with self._lock:
            client = self._client
            self._client = None
        if client is not None:
            client.close()
