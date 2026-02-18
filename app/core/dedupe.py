from __future__ import annotations

import time
from typing import Protocol


class DedupeStore(Protocol):
    async def seen(self, provider: str, message_id: str) -> bool: ...
    async def mark(self, provider: str, message_id: str, ttl_sec: int | None = None, payload_hash: str | None = None) -> bool: ...
    async def cleanup(self) -> int: ...


class MemoryDedupeStore:
    def __init__(self, ttl_sec: int = 3600):
        self.ttl_sec = ttl_sec
        # key = f"{provider}:{message_id}" -> first_seen_epoch
        self._store: dict[str, int] = {}

    async def seen(self, provider: str, message_id: str) -> bool:
        self._cleanup()
        key = f"{provider}:{message_id}"
        return key in self._store

    async def mark(
        self,
        provider: str,
        message_id: str,
        ttl_sec: int | None = None,
        payload_hash: str | None = None,
    ) -> bool:
        # payload_hash no se usa en memoria, se deja por compatibilidad de interfaz
        self._cleanup()
        key = f"{provider}:{message_id}"
        if key in self._store:
            return False
        self._store[key] = int(time.time())
        return True

    async def cleanup(self) -> int:
        return self._cleanup()

    def _cleanup(self) -> int:
        now = int(time.time())
        ttl = self.ttl_sec
        expired = [k for k, ts in self._store.items() if now - ts > ttl]
        for k in expired:
            self._store.pop(k, None)
        return len(expired)