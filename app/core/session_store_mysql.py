from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy import text

from app.infra.db import get_db_session


class MySQLSessionStore:
    def __init__(self, ttl_sec: int = 3600):
        self.ttl_sec = ttl_sec

    # -----------------------
    # ASYNC API (compat)
    # -----------------------
    async def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        return self.get_sync(session_id)

    async def set(self, session_id: str, session_data: Dict[str, Any]) -> None:
        self.set_sync(session_id, session_data)

    async def cleanup(self) -> int:
        return self.cleanup_sync()

    # -----------------------
    # SYNC API (lo que usa tu orchestrator hoy)
    # -----------------------
    def get_sync(self, session_id: str) -> Optional[Dict[str, Any]]:
        db = get_db_session()
        try:
            row = db.execute(
                text(
                    """
                    SELECT history_json, facts_json, expires_at
                    FROM sessions
                    WHERE session_id = :session_id
                    LIMIT 1
                    """
                ),
                {"session_id": session_id},
            ).fetchone()

            if not row:
                return None

            history_json, facts_json, expires_at = row

            if expires_at is not None:
                now = datetime.now(timezone.utc).replace(tzinfo=None)
                if expires_at < now:
                    return None

            return {
                "history": json.loads(history_json) if history_json else [],
                "facts": json.loads(facts_json) if facts_json else {},
            }
        finally:
            db.close()

    def set_sync(self, session_id: str, session_data: Dict[str, Any]) -> None:
        history = session_data.get("history", [])
        facts = session_data.get("facts", {})

        now_utc = datetime.now(timezone.utc)
        expires_at = (now_utc + timedelta(seconds=self.ttl_sec)).replace(tzinfo=None)

        db = get_db_session()
        try:
            db.execute(
                text(
                    """
                    INSERT INTO sessions (session_id, history_json, facts_json, expires_at)
                    VALUES (:session_id, :history_json, :facts_json, :expires_at)
                    ON DUPLICATE KEY UPDATE
                      history_json = VALUES(history_json),
                      facts_json = VALUES(facts_json),
                      expires_at = VALUES(expires_at),
                      updated_at = CURRENT_TIMESTAMP
                    """
                ),
                {
                    "session_id": session_id,
                    "history_json": json.dumps(history, ensure_ascii=False),
                    "facts_json": json.dumps(facts, ensure_ascii=False),
                    "expires_at": expires_at,
                },
            )
            db.commit()
        finally:
            db.close()

    def cleanup_sync(self) -> int:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        db = get_db_session()
        try:
            res = db.execute(
                text("DELETE FROM sessions WHERE expires_at IS NOT NULL AND expires_at < :now"),
                {"now": now},
            )
            db.commit()
            return int(res.rowcount or 0)
        finally:
            db.close()