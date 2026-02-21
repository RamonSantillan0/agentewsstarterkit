from __future__ import annotations

import json
import secrets
from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


def _gen_short_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"  # 000000-999999


class MySQLConfirmationStore:
    def __init__(self, ttl_sec: int = 600):
        self.ttl_sec = ttl_sec

    def create(
        self,
        db: Session,
        session_id: str,
        tool_name: str,
        tool_args: Dict[str, Any],
        ttl_sec: Optional[int] = None,
    ) -> Dict[str, str]:
        token = secrets.token_urlsafe(16)
        ttl = int(ttl_sec or self.ttl_sec)

        # Generar short_code y evitar colisiones
        short_code = None
        for _ in range(10):
            candidate = _gen_short_code()
            exists = db.execute(
                text("SELECT 1 FROM pending_confirmations WHERE short_code=:c LIMIT 1"),
                {"c": candidate},
            ).first()
            if not exists:
                short_code = candidate
                break

        # Si por alguna razón no conseguimos uno, seguimos sin short_code (no debería pasar)
        db.execute(
            text(
                """
                INSERT INTO pending_confirmations
                (token, short_code, session_id, tool_name, tool_args_json, status, created_at, expires_at)
                VALUES
                (:token, :short_code, :session_id, :tool_name, :tool_args_json, 'pending', UTC_TIMESTAMP(),
                 DATE_ADD(UTC_TIMESTAMP(), INTERVAL :ttl SECOND))
                """
            ),
            {
                "token": token,
                "short_code": short_code,
                "session_id": session_id,
                "tool_name": tool_name,
                "tool_args_json": json.dumps(tool_args, ensure_ascii=False),
                "ttl": ttl,
            },
        )
        db.commit()

        return {"token": token, "short_code": short_code or token}

    def consume(self, db: Session, token_or_code: str, session_id: str) -> Optional[Dict[str, Any]]:
        # lock row (evita doble consumo)
        row = db.execute(
            text(
                """
                SELECT token, short_code, session_id, tool_name, tool_args_json, status, expires_at
                FROM pending_confirmations
                WHERE token = :v OR short_code = :v
                FOR UPDATE
                """
            ),
            {"v": token_or_code},
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
        if expires_at is not None and expires_at < db.execute(text("SELECT UTC_TIMESTAMP()")).scalar_one():
            db.execute(
                text("UPDATE pending_confirmations SET status='expired' WHERE token=:token"),
                {"token": row["token"]},
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
            {"token": row["token"]},
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