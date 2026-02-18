from __future__ import annotations

import json
import secrets
from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


class MySQLConfirmationStore:
    def __init__(self, ttl_sec: int = 600):
        self.ttl_sec = ttl_sec

    def create(
        self,
        db: Session,
        session_id: str,
        tool_name: str,
        tool_args: Dict[str, Any],
        ttl_sec: Optional[int] = None,   # ✅ nuevo
    ) -> str:
        token = secrets.token_urlsafe(16)
        ttl = int(ttl_sec or self.ttl_sec)  # ✅ usa override si viene

        db.execute(
            text(
                """
                INSERT INTO pending_confirmations
                (token, session_id, tool_name, tool_args_json, status, created_at, expires_at)
                VALUES
                (:token, :session_id, :tool_name, :tool_args_json, 'pending', UTC_TIMESTAMP(),
                DATE_ADD(UTC_TIMESTAMP(), INTERVAL :ttl SECOND))
                """
            ),
            {
                "token": token,
                "session_id": session_id,
                "tool_name": tool_name,
                "tool_args_json": json.dumps(tool_args, ensure_ascii=False),
                "ttl": ttl,  # ✅ antes: self.ttl_sec
            },
        )
        db.commit()
        return token

    def consume(self, db: Session, token: str, session_id: str) -> Optional[Dict[str, Any]]:
        # lock row (evita doble consumo)
        row = db.execute(
            text(
                """
                SELECT token, session_id, tool_name, tool_args_json, status, expires_at
                FROM pending_confirmations
                WHERE token = :token
                FOR UPDATE
                """
            ),
            {"token": token},
        ).mappings().first()

        if not row:
            db.rollback()
            return None

        if row["session_id"] != session_id:
            db.rollback()
            return None

        if row["status"] != "pending":
            db.rollback()
            return None

        expires_at = row["expires_at"]
        # expires_at viene como datetime (normalmente). Si está vencido, marcar expired.
        if expires_at is not None and expires_at < db.execute(text("SELECT UTC_TIMESTAMP()")).scalar_one():
            db.execute(
                text("UPDATE pending_confirmations SET status='expired' WHERE token=:token"),
                {"token": token},
            )
            db.commit()
            return None

        # consumir
        db.execute(
            text(
                """
                UPDATE pending_confirmations
                SET status='consumed', consumed_at=UTC_TIMESTAMP()
                WHERE token=:token AND status='pending'
                """
            ),
            {"token": token},
        )
        db.commit()

        raw_args = row["tool_args_json"]
        if isinstance(raw_args, (bytes, bytearray)):
            raw_args = raw_args.decode("utf-8", errors="replace")

        return {
            "session_id": row["session_id"],
            "tool_name": row["tool_name"],
            "tool_args": json.loads(raw_args),
        }

    def cleanup_expired(self, db: Session) -> int:
        res = db.execute(
            text(
                """
                UPDATE pending_confirmations
                SET status='expired'
                WHERE status='pending' AND expires_at IS NOT NULL AND expires_at < UTC_TIMESTAMP()
                """
            )
        )
        db.commit()
        return res.rowcount or 0


confirmations_store = MySQLConfirmationStore(ttl_sec=600)