from __future__ import annotations

from fastapi import APIRouter

from app.api.channels.web import router as web_router
from app.api.channels.whatsapp import router as wa_router
from app.api.channels.provider_webhook import router as provider_router

router = APIRouter()
router.include_router(web_router)
router.include_router(wa_router)
router.include_router(provider_router)