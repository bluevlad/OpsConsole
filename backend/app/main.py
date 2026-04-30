"""OpsConsole FastAPI entrypoint.

P0 §0 단계: /api/health 한 개만 우선 노출. 라우터 추가는 §2에서 진행.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.core.config import settings


def create_app() -> FastAPI:
    app = FastAPI(
        title="OpsConsole API",
        version="0.0.1",
        description="멀티 서비스 운영 콘솔 — 카탈로그/콘텐츠/헬스/변경요청",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router, prefix="/api")

    return app


app = create_app()
