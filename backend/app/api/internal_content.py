"""GET /api/internal/content/published — 본 서비스(예: AllergyInsight)가 polling 하는 endpoint.

인증: X-Ops-Internal-Token 헤더 (settings.ops_internal_token).
응답: { service_code: { section_code: { key: { locale: { body, version, published_at }}}}}.

ETag/Last-Modified 지원 — 304 Not Modified 시 본 서비스 캐시 그대로 사용.

설계:
- 사용자 JWT 사용 안 함 (별도 공유 비밀)
- service_code 쿼리 파라미터로 필터링 가능 (예: ?service=allergyinsight)
- 같은 client 가 5분 polling 해도 ETag 일치 시 304
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from app.core.config import settings
from app.database.session import get_db
from app.models.content import OpsContentBlock
from app.models.section import OpsSection
from app.models.service import OpsService

router = APIRouter(prefix="/internal/content", tags=["internal-content"])


def _check_token(x_ops_internal_token: str | None) -> None:
    if not settings.ops_internal_token:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "OPS_INTERNAL_TOKEN 미설정 — 내부 endpoint 비활성",
        )
    if not x_ops_internal_token or x_ops_internal_token != settings.ops_internal_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid X-Ops-Internal-Token")


@router.get("/published")
async def list_published(
    response: Response,
    service: str | None = Query(default=None),
    x_ops_internal_token: str | None = Header(default=None, alias="X-Ops-Internal-Token"),
    if_none_match: str | None = Header(default=None, alias="If-None-Match"),
    db: AsyncSession = Depends(get_db),
):
    _check_token(x_ops_internal_token)

    svc_stmt = select(OpsService)
    if service:
        svc_stmt = svc_stmt.where(OpsService.code == service)
    services = (await db.execute(svc_stmt)).scalars().all()
    if not services:
        return _emit({}, response, if_none_match)

    service_ids = [s.id for s in services]
    sections = (
        await db.execute(
            select(OpsSection).where(OpsSection.service_id.in_(service_ids))
        )
    ).scalars().all()
    if not sections:
        return _emit({s.code: {} for s in services}, response, if_none_match)

    blocks = (
        await db.execute(
            select(OpsContentBlock).where(
                OpsContentBlock.section_id.in_([s.id for s in sections]),
                OpsContentBlock.status == "published",
            )
        )
    ).scalars().all()

    svc_by_id = {s.id: s for s in services}
    sec_by_id = {s.id: s for s in sections}

    payload: dict = {svc.code: {} for svc in services}
    last_published: datetime | None = None

    for b in blocks:
        sec = sec_by_id.get(b.section_id)
        if sec is None:
            continue
        svc = svc_by_id.get(sec.service_id)
        if svc is None:
            continue
        sec_dict = payload.setdefault(svc.code, {}).setdefault(sec.code, {})
        key_dict = sec_dict.setdefault(b.key, {})
        key_dict[b.locale] = {
            "body": b.published_body,
            "format": b.format,
            "version": b.published_version,
            "published_at": b.published_at.isoformat() if b.published_at else None,
        }
        if b.published_at and (last_published is None or b.published_at > last_published):
            last_published = b.published_at

    if last_published is not None:
        response.headers["Last-Modified"] = last_published.strftime(
            "%a, %d %b %Y %H:%M:%S GMT"
        )

    return _emit(payload, response, if_none_match)


def _emit(payload: dict, response: Response, if_none_match: str | None):
    """ETag 비교 후 304 또는 payload 반환."""
    body = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    etag = '"' + hashlib.sha256(body).hexdigest()[:32] + '"'
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "private, max-age=0"
    if if_none_match and if_none_match.strip() == etag:
        response.status_code = 304
        return Response(status_code=304, headers=response.headers)
    return payload
