"""GET /api/health — P0 §0 부트스트랩 헬스 엔드포인트."""
from datetime import datetime, timezone

from fastapi import APIRouter

from app.core.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "service": "opsconsole-backend",
        "env": settings.app_env,
        "version": "0.0.1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
