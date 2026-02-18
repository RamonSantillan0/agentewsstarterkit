from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, ConfigDict


class AgentRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class WAAgentRequest(BaseModel):
    from_number: str
    text: str
    message_id: Optional[str] = None


class UserMessage(BaseModel):
    message: str
    session_id: Optional[str]
    channel: str
    user_id: Optional[str]
    message_id: Optional[str]
    raw: Optional[Dict[str, Any]] = None


class ToolCall(BaseModel):
    name: str
    args: Dict[str, Any] = Field(default_factory=dict)
    requires_confirmation: bool = False


PlannerIntent = Literal["identify", "faq", "read_data", "write_action", "unknown"]


class PlannerSlots(BaseModel):
    cliente_ref: Optional[str] = None
    periodo: Optional[str] = None
    otros: Dict[str, Any] = Field(default_factory=dict)


class PlannerOutput(BaseModel):
    intent: PlannerIntent
    slots: PlannerSlots = Field(default_factory=PlannerSlots)
    missing: List[Literal["cliente_ref", "periodo"]] = Field(default_factory=list)
    tool_calls: List[ToolCall] = Field(default_factory=list)
    final: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)

    model_config = ConfigDict(extra="ignore")


class AgentResponse(BaseModel):
    intent: str
    reply: str
    missing: List[str] = Field(default_factory=list)
    data: Dict[str, Any] = Field(default_factory=dict)
    debug: Optional[Dict[str, Any]] = None