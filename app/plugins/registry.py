from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.infra.utils import import_from_path
from app.plugins.base import Tool


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    @classmethod
    def from_settings(cls, settings: Any) -> "ToolRegistry":
        reg = cls()
        provider_fn = import_from_path(settings.TOOLS_PROVIDER)
        provided = provider_fn()
        reg.register_many(provided)
        return reg

    def register_many(self, tools: Any) -> None:
        """
        tools puede ser list[Tool] o dict[name, Tool]
        """
        if isinstance(tools, dict):
            items = tools.items()
        else:
            items = [(t.name, t) for t in tools]

        for name, tool in items:
            self._tools[name] = tool

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def list(self) -> List[Tool]:
        return list(self._tools.values())

    def describe_tools(self) -> str:
        """
        Catálogo para el planner (texto) incluyendo ARGS reales desde el input_model.

        Esto evita que el LLM invente nombres de parámetros.
        """
        lines: List[str] = []
        for t in self.list():
            scopes = ",".join(t.scopes or [])
            confirm_note = " (requires_confirmation)" if "write" in (t.scopes or []) else ""

            # Schema de args (Pydantic v2)
            args_schema = {}
            required: List[str] = []
            try:
                schema = t.input_model.model_json_schema()  # type: ignore[attr-defined]
                args_schema = schema.get("properties", {}) or {}
                required = schema.get("required", []) or []
            except Exception:
                args_schema = {}
                required = []

            # Formateo args
            if not args_schema:
                args_desc = "args: (none)"
            else:
                parts: List[str] = []
                for field_name, meta in args_schema.items():
                    ftype = meta.get("type", "any")
                    fdesc = meta.get("description", "")
                    req = "required" if field_name in required else "optional"
                    if fdesc:
                        parts.append(f"{field_name}:{ftype} ({req}) - {fdesc}")
                    else:
                        parts.append(f"{field_name}:{ftype} ({req})")
                args_desc = "args: " + "; ".join(parts)

            lines.append(f"- {t.name} ({scopes}){confirm_note}: {t.description}\n  {args_desc}")

        return "\n".join(lines)