from __future__ import annotations

from typing import Any, Dict, List, Protocol, Type

from pydantic import BaseModel


class Tool(Protocol):
    name: str
    description: str
    input_model: Type[BaseModel]
    scopes: List[str]  # ["read"] or ["write"]

    async def run(self, args: BaseModel, ctx: Dict[str, Any]) -> Dict[str, Any]: ...