from __future__ import annotations

import json
from typing import Any, Dict, Optional

from sqlalchemy import text

from app.infra.db import get_db_session


class MySQLAuditStore:
    def append(
        self,
        *,
        request_id: str,
        session_id: str,
        type: str,
        channel: Optional[str] = None,
        intent: Optional[str] = None,
        tool_name: Optional[str] = None,
        confirmed: Optional[bool] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        db = get_db_session()
        try:
            db.execute(
                text(
                    """
                    INSERT INTO audit_events
                      (request_id, session_id, type, channel, intent, tool_name, confirmed, payload_json)
                    VALUES
                      (:request_id, :session_id, :type, :channel, :intent, :tool_name, :confirmed, :payload_json)
                    """
                ),
                {
                    "request_id": request_id,
                    "session_id": session_id,
                    "type": type,
                    "channel": channel,
                    "intent": intent,
                    "tool_name": tool_name,
                    "confirmed": 1 if confirmed else 0 if confirmed is not None else None,
                    "payload_json": json.dumps(payload, ensure_ascii=False) if payload is not None else None,
                },
            )
            db.commit()
        finally:
            db.close()