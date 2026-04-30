"""OpsConsole FastAPI entrypoint."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.catalog import router as catalog_router
from app.api.change_requests import router as change_requests_router
from app.api.content import router as content_router
from app.api.github_webhook import router as github_webhook_router
from app.api.health import router as health_router
from app.api.health_api import router as health_api_router
from app.api.internal_content import router as internal_content_router
from app.api.my import router as my_router
from app.api.permissions import router as permissions_router
from app.core.config import settings
from app.jobs.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    try:
        yield
    finally:
        stop_scheduler()


def create_app() -> FastAPI:
    app = FastAPI(
        title="OpsConsole API",
        version="0.1.0",
        description="멀티 서비스 운영 콘솔 — 카탈로그/콘텐츠/헬스/변경요청",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router, prefix="/api")
    app.include_router(auth_router, prefix="/api")
    app.include_router(catalog_router, prefix="/api")
    app.include_router(my_router, prefix="/api")
    app.include_router(permissions_router, prefix="/api")
    app.include_router(health_api_router, prefix="/api")
    app.include_router(change_requests_router, prefix="/api")
    app.include_router(github_webhook_router, prefix="/api")
    app.include_router(content_router, prefix="/api")
    app.include_router(internal_content_router, prefix="/api")

    return app


app = create_app()
