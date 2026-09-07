import hashlib
from collections.abc import Awaitable
from functools import lru_cache
from typing import cast

from fastapi import HTTPException
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings

WINDOW_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return count
"""


@lru_cache
def rate_limit_store() -> Redis:
    return cast(
        Redis, Redis.from_url(get_settings().redis_url, socket_connect_timeout=2, socket_timeout=2)
    )


async def enforce_rate_limit(scope: str, identity: str, limit: int, seconds: int) -> None:
    digest = hashlib.sha256(identity.encode()).hexdigest()
    try:
        count = await cast(
            Awaitable[int],
            rate_limit_store().eval(WINDOW_SCRIPT, 1, f"cos:limit:{scope}:{digest}", str(seconds)),
        )
    except RedisError:
        # Never silently remove brute-force protection during a Redis outage.
        raise HTTPException(
            status_code=503, detail="Authentication temporarily unavailable"
        ) from None
    if int(count) > limit:
        raise HTTPException(
            status_code=429,
            detail="Too many attempts; try again later",
            headers={"Retry-After": str(seconds)},
        )
