"""Simple in-memory rate limiter for Kolibri API."""
import os
import time
from collections import defaultdict
from typing import Dict, Tuple
from fastapi import Request, HTTPException


class RateLimiter:
    """In-memory rate limiter using sliding window."""

    def __init__(self, requests_per_minute: int = 60):
        self.rpm = max(0, int(requests_per_minute))
        self._requests: Dict[str, list] = defaultdict(list)

    def check(self, key: str) -> bool:
        """Check if request is allowed. Returns True if allowed."""
        if self.rpm <= 0:
            return True
        now = time.time()
        window = 60.0  # 1 minute

        # Clean old entries
        self._requests[key] = [t for t in self._requests[key] if now - t < window]

        if len(self._requests[key]) >= self.rpm:
            return False

        self._requests[key].append(now)
        return True

    def get_remaining(self, key: str) -> int:
        """Get remaining requests in current window."""
        if self.rpm <= 0:
            return 0
        now = time.time()
        window = 60.0
        recent = [t for t in self._requests[key] if now - t < window]
        return max(0, self.rpm - len(recent))


def _read_env_rpm(name: str, default: int) -> int:
    """Read an RPM limit from env; keep legacy defaults when value is missing/invalid."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return max(0, int(str(raw).strip()))
    except ValueError:
        return default


# Global instances
api_limiter = RateLimiter(requests_per_minute=_read_env_rpm("KOLIBRI_API_RATE_LIMIT_RPM", 120))
chat_limiter = RateLimiter(requests_per_minute=_read_env_rpm("KOLIBRI_CHAT_RATE_LIMIT_RPM", 30))
auth_limiter = RateLimiter(requests_per_minute=_read_env_rpm("KOLIBRI_AUTH_RATE_LIMIT_RPM", 10))


def get_client_ip(request: Request) -> str:
    """Extract client IP from request."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def check_rate_limit(request: Request, limiter: RateLimiter = api_limiter):
    """FastAPI dependency for rate limiting."""
    client_ip = get_client_ip(request)
    if not limiter.check(client_ip):
        remaining = limiter.get_remaining(client_ip)
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"X-RateLimit-Remaining": str(remaining), "Retry-After": "60"},
        )
