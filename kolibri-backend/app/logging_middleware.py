"""Structured logging middleware for Kolibri API."""
import time
import logging
import json
import os
import re
import uuid
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("kolibri")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9._:-]{1,120}$")


def release_id() -> str:
    value = os.getenv("KOLIBRI_RELEASE_ID", "").strip()
    return value if _IDENTIFIER.fullmatch(value) else "unversioned"


class ReleaseIdentityMiddleware(BaseHTTPMiddleware):
    """Attach one release identity and request ID to every HTTP response."""

    async def dispatch(self, request: Request, call_next):
        supplied = request.headers.get("X-Request-ID", "").strip()
        request_id = supplied if _IDENTIFIER.fullmatch(supplied) else f"req_{uuid.uuid4().hex}"
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Kolibri-Release"] = release_id()
        response.headers["X-Request-ID"] = request_id
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log all requests with timing and status."""

    async def dispatch(self, request: Request, call_next):
        start = time.time()
        response = await call_next(request)
        duration_ms = round((time.time() - start) * 1000, 1)

        log_entry = {
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": duration_ms,
            "client": request.client.host if request.client else "unknown",
        }

        if response.status_code >= 400:
            logger.warning(json.dumps(log_entry, ensure_ascii=False))
        elif duration_ms > 5000:
            logger.warning(json.dumps(log_entry, ensure_ascii=False))
        else:
            logger.info(json.dumps(log_entry, ensure_ascii=False))

        return response


def setup_logging():
    """Configure structured logging."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        handlers=[logging.StreamHandler()],
    )
