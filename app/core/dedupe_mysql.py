from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.infra.db import get_db_session


def sha256_payload(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


class MySQLDedupeStore:
    def __init__(self, ttl_sec_default: int = 3600):
        self.ttl_sec_default = ttl_sec_default

    async def seen(self, provider: str, message_id: str) -> bool:
        db = get_db_session()
        try:
            row = db.execute(
                text(
                    """
                    SELECT 1
                    FROM dedupe_messages
                    WHERE provider = :provider AND message_id = :message_id
                    LIMIT 1
                    """
                ),
                {"provider": provider, "message_id": message_id},
            ).fetchone()
            return row is not None
        finally:
            db.close()

    async def mark(
        self,
        provider: str,
        message_id: str,
        ttl_sec: int | None = None,
        payload_hash: str | None = None,
    ) -> bool:
        ttl = ttl_sec or self.ttl_sec_default
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=ttl)).replace(tzinfo=None)

        db = get_db_session()
        try:
            try:
                db.execute(
                    text(
                        """
                        INSERT INTO dedupe_messages
                          (provider, message_id, first_seen_at, expires_at, payload_hash)
                        VALUES
                          (:provider, :message_id, :first_seen_at, :expires_at, :payload_hash)
                        """
                    ),
                    {
                        "provider": provider,
                        "message_id": message_id,
                        "first_seen_at": now,
                        "expires_at": expires_at,
                        "payload_hash": payload_hash,
                    },
                )
                db.commit()
                return True
            except IntegrityError:
                db.rollback()
                return False
        finally:
            db.close()

    async def cleanup(self) -> int:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        db = get_db_session()
        try:
            res = db.execute(
                text("DELETE FROM dedupe_messages WHERE expires_at < :now"),
                {"now": now},
            )
            db.commit()
            return int(res.rowcount or 0)
        finally:
            db.close()