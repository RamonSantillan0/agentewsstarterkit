from __future__ import annotations

import json
import time
from fastapi import APIRouter, Header, HTTPException, Request

from app.agent.orchestrator import AgentOrchestrator
from app.agent.schema import AgentResponse, UserMessage
from app.core.security import verify_webhook_signature
from app.core.events import EventBus
from app.core.session_store_mysql import MySQLSessionStore

from app.core.dedupe_mysql import MySQLDedupeStore, sha256_payload
from app.plugins.registry import ToolRegistry
from app.settings import settings

from app.core.audit_writer_mysql import MySQLAuditWriter
from app.core.events import EventBus




router = APIRouter()

event_bus = EventBus(writer=MySQLAuditWriter())

session_store = MySQLSessionStore(ttl_sec=settings.SESSION_TTL_SEC)

dedupe_store = MySQLDedupeStore(ttl_sec_default=settings.DEDUPE_TTL_SEC)
tool_registry = ToolRegistry.from_settings(settings)

orchestrator = AgentOrchestrator(
    settings=settings,
    tool_registry=tool_registry,
    session_store=session_store,
    dedupe_store=dedupe_store,
    event_bus=event_bus,
)


@router.post("/provider/inbound", response_model=AgentResponse)
async def provider_inbound(
    request: Request,
    provider_signature: str = Header(default="", alias="provider-signature"),
    provider_timestamp: str = Header(default="", alias="provider-timestamp"),
):
    raw_bytes = await request.body()

    # ✅ Límite de tamaño del body (evita payloads gigantes / abuso)
    if len(raw_bytes) > 256_000:  # 256 KB
        raise HTTPException(status_code=413, detail="Payload too large")

    # ✅ Anti-replay genérico por timestamp (si viene)
    if provider_timestamp:
        try:
            ts = int(provider_timestamp)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid provider-timestamp")

        now = int(time.time())
        window = settings.WEBHOOK_REPLAY_WINDOW_SEC
        max_future = getattr(settings, "WEBHOOK_MAX_FUTURE_SKEW_SEC", 30)

        if ts < (now - window):
            raise HTTPException(status_code=401, detail="Stale request (replay window)")
        if ts > (now + max_future):
            raise HTTPException(status_code=401, detail="Request timestamp too far in future")

    # ✅ Firma solo si está habilitada (cuando definas proveedor)
    if settings.WEBHOOK_VERIFY_SIGNATURE:
        ok = verify_webhook_signature(
            body=raw_bytes,
            signature=provider_signature,
            timestamp=provider_timestamp,
            secret=settings.WEBHOOK_SECRET,
            replay_window_sec=settings.WEBHOOK_REPLAY_WINDOW_SEC,
        )
        if not ok:
            raise HTTPException(status_code=401, detail="Invalid signature")

    # Parse JSON
    try:
        payload = json.loads(raw_bytes.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    text = str(payload.get("message", "")).strip()
    text = text[:2000]  # ✅ límite texto

    from_id = str(payload.get("from", "")).strip() or None

    incoming_id = payload.get("message_id") or payload.get("id")
    message_id = str(incoming_id) if incoming_id else sha256_payload(raw_bytes)

    if not text:
        raise HTTPException(status_code=400, detail="Missing message")

    provider = "provider_webhook"

    msg = UserMessage(
        message=text,
        session_id=from_id or "provider_session",
        channel=provider,
        user_id=from_id,
        message_id=message_id,
        raw=payload,
    )

    # ✅ Pasamos hash del body al orchestrator para guardarlo en dedupe_messages
    headers = dict(request.headers)
    headers["x-payload-hash"] = sha256_payload(raw_bytes)

    return await orchestrator.handle_message(msg, request_headers=headers)