from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from typing import Any


logger = logging.getLogger("app")


def configure_logging(env: str = "dev") -> None:
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())
    logger.handlers = [handler]
    logger.propagate = False


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "msg": record.getMessage(),
        }
        # extras
        if hasattr(record, "extra") and isinstance(record.extra, dict):
            base.update(record.extra)
        return json.dumps(base, ensure_ascii=False)


def log_event(event: str, **fields: Any) -> None:
    logger.info(event, extra={"extra": fields})