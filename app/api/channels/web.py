from __future__ import annotations

from fastapi import APIRouter, Request

from app.agent.orchestrator import AgentOrchestrator
from app.agent.schema import AgentRequest, AgentResponse, UserMessage
from app.core.events import EventBus
from app.core.session_store_mysql import MySQLSessionStore
from app.core.dedupe import MemoryDedupeStore
from app.plugins.registry import ToolRegistry
from app.settings import settings

from app.core.audit_writer_mysql import MySQLAuditWriter
from app.core.events import EventBus


router = APIRouter()

# singletons (starter kit)
event_bus = EventBus(writer=MySQLAuditWriter())
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


@router.post("/agent", response_model=AgentResponse)
async def agent_endpoint(payload: AgentRequest, request: Request):
    msg = UserMessage(
        message=payload.message,
        session_id=payload.session_id,
        channel="web",
        user_id=None,
        message_id=None,
        raw=None,
    )
    return await orchestrator.handle_message(msg, request_headers=dict(request.headers))