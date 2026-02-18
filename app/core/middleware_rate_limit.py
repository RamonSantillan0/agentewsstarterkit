from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.settings import settings
from app.core.rate_limit import MemoryFixedWindowLimiter


class RateLimitIPMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.limiter = MemoryFixedWindowLimiter(
            max_requests=settings.RATE_LIMIT_IP_MAX,
            window_sec=settings.RATE_LIMIT_IP_WINDOW_SEC,
        )

    async def dispatch(self, request: Request, call_next):
        if not settings.RATE_LIMIT_ENABLED:
            return await call_next(request)

        ip = request.client.host if request.client else "unknown"
        res = self.limiter.check(f"ip:{ip}")

        if not res.allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit (ip) exceeded", "retry_after_sec": res.retry_after_sec},
                headers={"Retry-After": str(res.retry_after_sec)},
            )

        return await call_next(request)