"""
TRACE API — Rate Limiting

Protects against:
- Login brute-force (10/min)
- Event spam / trust graph poisoning (120/min)
- Benchmark CPU DoS (5/min)
- General API abuse (60/min default)

Uses Redis as backend in production. Falls back to in-memory storage
for local development when Redis is unavailable.
"""

import logging
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request
from fastapi.responses import JSONResponse

from .config import settings

logger = logging.getLogger("trace.rate_limit")

# Try Redis first, fall back to in-memory for local dev
try:
    limiter = Limiter(
        key_func=get_remote_address,
        storage_uri=settings.redis_url
    )
    logger.info(f"Rate limiter using Redis: {settings.redis_url}")
except Exception as e:
    logger.warning(f"Redis unavailable for rate limiting ({e}), falling back to in-memory storage")
    limiter = Limiter(
        key_func=get_remote_address,
        storage_uri="memory://"
    )

# Rate limit strings — override via environment
RATE_LIMIT_DEFAULT = settings.rate_limit_default
RATE_LIMIT_AUTH = settings.rate_limit_auth
RATE_LIMIT_EVENTS = settings.rate_limit_events
RATE_LIMIT_BENCHMARK = settings.rate_limit_benchmark

async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={
            "detail": f"Rate limit exceeded: {exc.detail}",
            "retry_after": str(exc.detail),
        },
    )
