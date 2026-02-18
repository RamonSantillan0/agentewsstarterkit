from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request

from app.agent.orchestrator import AgentOrchestrator
from app.agent.schema import WAAgentRequest, AgentResponse, UserMessage
from app.core.events import EventBus
from app.core.session_store_mysql import MySQLSessionStore
from app.core.dedupe import MemoryDedupeStore
from app.plugins.registry import ToolRegistry
from app.settings import settings

router = APIRouter()

event_bus = EventBus()
session_store = MySQLSessionStore(ttl_sec=settings.SESSION_TTL_SEC)
dedupe_store = MemoryDedupeStore(ttl_sec=settings.DEDUPE_TTL_SEC)
tool_registry = ToolRegistry.from_settings(settings)

orchestrator = AgentOrchestrator(
    settings=settings,
    tool_registry=tool_registry,
    session_store=session_store,
    dedupe_store=dedupe_store,
    event_bus=event_bus,
)


@router.post("/wa/agent", response_model=AgentResponse)
async def wa_agent_endpoint(
    payload: WAAgentRequest,
    request: Request,
    x_api_key: str = Header(default="", alias="x-api-key"),
):
    if not settings.INTERNAL_API_KEY or x_api_key != settings.INTERNAL_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # session_id por número para canal WA
    session_id = payload.from_number

    msg = UserMessage(
        message=payload.text,
        session_id=session_id,
        channel="whatsapp",
        user_id=payload.from_number,
        message_id=payload.message_id,
        raw=payload.model_dump(),
    )
    return await orchestrator.handle_message(msg, request_headers=dict(request.headers))