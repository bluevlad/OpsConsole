"""Slack Incoming Webhook 클라이언트.

settings.slack_webhook_url 미설정 시 no-op (로깅만).
"""
from __future__ import annotations

import logging

import httpx

from app.core.config import settings

log = logging.getLogger("opsconsole.notify.slack")


async def send_to_slack(text: str, *, blocks: list[dict] | None = None, timeout_s: float = 5.0) -> bool:
    """Slack 웹훅 발송. 성공 True, 미설정/실패 False."""
    if not settings.slack_webhook_url:
        log.info("[slack] no webhook configured, skipping: %s", text[:100])
        return False

    payload: dict = {"text": text}
    if blocks:
        payload["blocks"] = blocks

    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            res = await client.post(settings.slack_webhook_url, json=payload)
        if res.status_code != 200:
            log.warning("[slack] webhook %s: %s", res.status_code, res.text[:200])
            return False
        return True
    except httpx.RequestError as e:
        log.warning("[slack] webhook request error: %s", e)
        return False
