from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from app.core.dedupe_mysql import MySQLDedupeStore
from app.core.session_store_mysql import MySQLSessionStore
from app.settings import settings

router = APIRouter(prefix="/admin/cleanup", tags=["admin"])


def _require_internal_key(x_api_key: str) -> None:
    if not settings.INTERNAL_API_KEY:
        raise HTTPException(status_code=500, detail="INTERNAL_API_KEY not set")
    if x_api_key != settings.INTERNAL_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.post("/dedupe")
async def cleanup_dedupe(x_api_key: str = Header(default="", alias="x-api-key")):
    _require_internal_key(x_api_key)
    store = MySQLDedupeStore(ttl_sec_default=settings.DEDUPE_TTL_SEC)
    deleted = await store.cleanup()
    return {"ok": True, "deleted": deleted}


@router.post("/sessions")
async def cleanup_sessions(x_api_key: str = Header(default="", alias="x-api-key")):
    _require_internal_key(x_api_key)
    store = MySQLSessionStore(ttl_sec=settings.SESSION_TTL_SEC)
    deleted = await store.cleanup()
    return {"ok": True, "deleted": deleted}

@router.post("/all")
async def cleanup_all(x_api_key: str = Header(default="", alias="x-api-key")):
    _require_internal_key(x_api_key)

    dedupe = MySQLDedupeStore(ttl_sec_default=settings.DEDUPE_TTL_SEC)
    sessions = MySQLSessionStore(ttl_sec=settings.SESSION_TTL_SEC)

    d = await dedupe.cleanup()
    s = await sessions.cleanup()

    return {"ok": True, "dedupe_deleted": d, "sessions_deleted": s}