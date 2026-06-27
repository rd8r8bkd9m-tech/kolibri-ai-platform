"""Structured logging middleware for Kolibri API."""
import time
import logging
import json
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("kolibri")


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
