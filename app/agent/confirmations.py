from __future__ import annotations

import secrets
import time
from typing import Any, Dict, Optional


class ConfirmationManager:
    """
    Maneja confirmaciones en 2 pasos para acciones write.
    Store simple en memoria. Se puede reemplazar por Redis/DB.
    """

    def __init__(self, ttl_sec: int = 600):
        self.ttl_sec = ttl_sec
        self._pending: dict[str, dict[str, Any]] = {}

    def create(
        self,
        session_id: str,
        tool_name: str,
        tool_args: Dict[str, Any],
        ttl_sec: Optional[int] = None,
    ) -> str:
        # Si no pasás ttl_sec, usa el TTL por defecto del manager
        ttl = int(ttl_sec) if ttl_sec is not None else int(self.ttl_sec)
        ttl = max(ttl, 1)  # evita TTL 0 o negativo

        now = int(time.time())
        token = secrets.token_urlsafe(16)

        self._pending[token] = {
            "session_id": session_id,
            "tool_name": tool_name,
            "tool_args": tool_args,
            "created_at": now,
            "expires_at": now + ttl,   # vencimiento absoluto
        }
        return token

    def consume(self, token: str, session_id: str) -> Optional[Dict[str, Any]]:
        item = self._pending.get(token)
        if not item:
            return None
        if item["session_id"] != session_id:
            return None

        now = int(time.time())
        expires_at = int(item.get("expires_at") or 0)

        # ✅ compat: si no existe expires_at, usar created_at + ttl_sec
        if expires_at:
            if now > expires_at:
                self._pending.pop(token, None)
                return None
        else:
            if now - int(item["created_at"]) > self.ttl_sec:
                self._pending.pop(token, None)
                return None

        self._pending.pop(token, None)
        return item

    def cleanup(self) -> None:
        now = int(time.time())
        expired = []
        for k, v in self._pending.items():
            expires_at = int(v.get("expires_at") or 0)
            if expires_at:
                if now > expires_at:
                    expired.append(k)
            else:
                if now - int(v["created_at"]) > self.ttl_sec:
                    expired.append(k)

        for k in expired:
            self._pending.pop(k, None)


# ✅ SINGLETON (esto evita que se “pierdan” tokens entre requests)
confirmations = ConfirmationManager(ttl_sec=1800)  # por defecto 30 min