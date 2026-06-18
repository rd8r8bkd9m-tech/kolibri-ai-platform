import time
import os
from typing import Optional

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

REDIS_URL = os.getenv("REDIS_URL", "redis://10.99.0.1:6379")
_rate_limit_redis: Optional[object] = None


async def get_redis():
    global _rate_limit_redis
    if _rate_limit_redis is None and REDIS_AVAILABLE:
        try:
            _rate_limit_redis = redis.from_url(REDIS_URL, decode_responses=True)
            await _rate_limit_redis.ping()
        except Exception:
            _rate_limit_redis = None
    return _rate_limit_redis


async def check_rate_limit_redis(ip: str, limit: int = 60, window: int = 60) -> bool:
    r = await get_redis()
    if r is None:
        return True

    key = f"ratelimit:{ip}"
    now = time.time()

    try:
        pipe = r.pipeline()
        pipe.zremrangebyscore(key, 0, now - window)
        pipe.zadd(key, {str(now): now})
        pipe.zcard(key)
        pipe.expire(key, window)
        results = await pipe.execute()
        count = results[2]
        return count <= limit
    except Exception:
        return True


async def cleanup_rate_limit_redis():
    r = await get_redis()
    if r:
        await r.close()
