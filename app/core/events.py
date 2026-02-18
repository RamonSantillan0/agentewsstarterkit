from __future__ import annotations

from typing import Any, Dict, List, Optional


class EventWriter:
    """Interfaz mínima para persistir eventos (DB/archivo/queue)."""
    def append(self, evt: Dict[str, Any]) -> None: ...


class EventBus:
    """
    Auditoría append-only (in-memory) + opcional persistencia via writer.
    """
    def __init__(self, writer: Optional[EventWriter] = None):
        self._events: List[Dict[str, Any]] = []
        self._writer = writer

    def append(self, evt: Dict[str, Any]) -> None:
        # siempre guardamos in-memory (útil en dev)
        self._events.append(evt)

        # si hay writer, persistimos, pero sin romper el request si falla
        if self._writer is not None:
            try:
                self._writer.append(evt)
            except Exception:
                pass

    def list(self) -> List[Dict[str, Any]]:
        return list(self._events)