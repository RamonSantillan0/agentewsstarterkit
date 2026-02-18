from __future__ import annotations

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.settings import settings
from app.api.health import router as health_router
from app.api.agent import router as agent_router
from app.api.db_test import router as db_test_router
from app.core.logging import configure_logging

from app.infra.db import engine
from app.infra.bootstrap import ensure_tables

from app.api.llm_test import router as llm_test_router
from app.api.planner_test import router as planner_test_router

from app.api.admin.cleanup import router as admin_cleanup_router

from app.core.middleware_rate_limit import RateLimitIPMiddleware






def create_app() -> FastAPI:
    configure_logging(env=settings.ENV)

    app = FastAPI(title=settings.APP_NAME)

    # Startup: asegurar tablas
    @app.on_event("startup")
    def startup() -> None:
        ensure_tables(engine)

    # CORS (ajustar en prod)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(agent_router)
    app.include_router(db_test_router)
    app.include_router(llm_test_router)
    app.include_router(planner_test_router)
    app.include_router(admin_cleanup_router)
    app.add_middleware(RateLimitIPMiddleware)

    return app


app = create_app()

if __name__ == "__main__":
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=(settings.ENV == "dev"))