"""GET /api/audit-log — ops_admin 전용 감사 로그 조회 (마스킹 적용)."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.masking import mask_payload
from app.core.security import require_role
from app.database.session import get_db
from app.models.audit import OpsAuditLog
from app.models.user import OpsUser

router = APIRouter(prefix="/audit-log", tags=["audit"])


class AuditEntryDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_id: int | None
    actor_email: str | None = None
    action: str
    target_type: str | None
    target_id: str | None
    payload: dict | None
    at: datetime


@router.get("", response_model=list[AuditEntryDTO])
async def list_audit(
    action: str | None = Query(default=None, description="action 정확 일치"),
    target_type: str | None = Query(default=None),
    actor_id: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    _admin: OpsUser = Depends(require_role("ops_admin")),
    db: AsyncSession = Depends(get_db),
) -> list[AuditEntryDTO]:
    stmt = select(OpsAuditLog).order_by(OpsAuditLog.id.desc())
    if action:
        stmt = stmt.where(OpsAuditLog.action == action)
    if target_type:
        stmt = stmt.where(OpsAuditLog.target_type == target_type)
    if actor_id is not None:
        stmt = stmt.where(OpsAuditLog.actor_id == actor_id)
    stmt = stmt.offset(offset).limit(limit)

    rows = (await db.execute(stmt)).scalars().all()

    # actor 이메일 매핑 (마스킹 적용)
    actor_ids = sorted({r.actor_id for r in rows if r.actor_id is not None})
    email_by_id: dict[int, str] = {}
    if actor_ids:
        from app.core.masking import mask_email

        users = (
            await db.execute(select(OpsUser).where(OpsUser.id.in_(actor_ids)))
        ).scalars().all()
        for u in users:
            email_by_id[u.id] = mask_email(u.email) or u.email

    out: list[AuditEntryDTO] = []
    for r in rows:
        out.append(
            AuditEntryDTO(
                id=r.id,
                actor_id=r.actor_id,
                actor_email=email_by_id.get(r.actor_id) if r.actor_id else None,
                action=r.action,
                target_type=r.target_type,
                target_id=r.target_id,
                payload=mask_payload(r.payload) if r.payload else None,
                at=r.at,
            )
        )
    return out
