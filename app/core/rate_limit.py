from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict


@dataclass
class RateLimitResult:
    allowed: bool
    retry_after_sec: int = 0


class MemoryFixedWindowLimiter:
    """
    Fixed window rate limiter (simple).
    Guarda timestamps por key y mantiene solo los de la ventana.
    """
    def __init__(self, max_requests: int, window_sec: int):
        self.max_requests = max_requests
        self.window_sec = window_sec
        self._buckets: Dict[str, Deque[float]] = {}

    def check(self, key: str) -> RateLimitResult:
        now = time.time()
        q = self._buckets.get(key)
        if q is None:
            q = deque()
            self._buckets[key] = q

        cutoff = now - self.window_sec
        while q and q[0] < cutoff:
            q.popleft()

        if len(q) >= self.max_requests:
            retry_after = int(max(1, (q[0] + self.window_sec) - now))
            return RateLimitResult(allowed=False, retry_after_sec=retry_after)

        q.append(now)
        return RateLimitResult(allowed=True)