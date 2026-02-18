from __future__ import annotations

import json
from typing import Any, Dict

from sqlalchemy import text

from app.infra.db import get_db_session


class MySQLAuditWriter:
    def append(self, evt: Dict[str, Any]) -> None:
        request_id = str(evt.get("request_id", ""))
        session_id = str(evt.get("session_id", ""))
        evt_type = str(evt.get("type", "UNKNOWN"))

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
                    "type": evt_type,
                    "channel": evt.get("channel"),
                    "intent": evt.get("intent"),
                    "tool_name": evt.get("tool_name"),
                    "confirmed": evt.get("confirmed"),
                    "payload_json": json.dumps(evt, ensure_ascii=False),
                },
            )
            db.commit()
        finally:
            db.close()