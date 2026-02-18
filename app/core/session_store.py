from __future__ import annotations

import time
from typing import Any, Dict, Optional, Protocol


class SessionStore(Protocol):
    async def get(self, session_id: str) -> Optional[Dict[str, Any]]: ...
    async def set(self, session_id: str, value: Dict[str, Any]) -> None: ...


class MemorySessionStore:
    def __init__(self, ttl_sec: int = 86400):
        self.ttl_sec = ttl_sec
        self._store: dict[str, dict[str, Any]] = {}

    async def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        self._cleanup()
        item = self._store.get(session_id)
        if not item:
            return None
        return item["value"]

    async def set(self, session_id: str, value: Dict[str, Any]) -> None:
        self._cleanup()
        self._store[session_id] = {"value": value, "ts": int(time.time())}

    # sync helpers (para simplificar orchestrator)
    def get_sync(self, session_id: str) -> Optional[Dict[str, Any]]:
        self._cleanup()
        item = self._store.get(session_id)
        return item["value"] if item else None

    def set_sync(self, session_id: str, value: Dict[str, Any]) -> None:
        self._cleanup()
        self._store[session_id] = {"value": value, "ts": int(time.time())}

    def _cleanup(self) -> None:
        now = int(time.time())
        expired = [k for k, v in self._store.items() if now - int(v["ts"]) > self.ttl_sec]
        for k in expired:
            self._store.pop(k, None)