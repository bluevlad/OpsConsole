"""POST /api/github/webhook — GitHub Issues / Pull request 이벤트 수신.

webhook 등록 (각 서비스 레포에 수동 1회):
  URL: https://opsconsole.unmong.com/api/github/webhook
  Content type: application/json
  Secret: GITHUB_WEBHOOK_SECRET (.env)
  Events: Issues, Pull requests (Pull request review 는 P3)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.database.session import get_db
from app.github import webhook_handler

router = APIRouter(prefix="/github", tags=["github"])


@router.post("/webhook")
async def receive_webhook(
    request: Request,
    x_github_event: str = Header(...),
    x_github_delivery: str = Header(...),
    x_hub_signature_256: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    body = await request.body()
    if not webhook_handler.verify_signature(
        settings.github_webhook_secret, body, x_hub_signature_256
    ):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "invalid X-Hub-Signature-256"
        )

    try:
        payload = await request.json()
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid JSON body")

    return await webhook_handler.handle_event(
        db,
        event_type=x_github_event,
        delivery_id=x_github_delivery,
        payload=payload,
    )
