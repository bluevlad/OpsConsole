"""GET /api/my/sections — 본인이 owner / backup / 권한 부여된 섹션."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dto import MySectionDTO
from app.core.security import get_current_user
from app.database.session import get_db
from app.models.permission import OpsSectionPermission
from app.models.section import OpsSection
from app.models.service import OpsService
from app.models.user import OpsUser
from app.services.health_summary import summarize_for_sections

router = APIRouter(prefix="/my", tags=["my"])


@router.get("/sections", response_model=list[MySectionDTO])
async def list_my_sections(
    user: OpsUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MySectionDTO]:
    """내가 owner / backup / permission 보유한 섹션 + 최근 헬스 요약."""
    # 1) owner / backup (이메일 기준)
    owner_or_backup_stmt = (
        select(OpsSection, OpsService)
        .join(OpsService, OpsSection.service_id == OpsService.id)
        .where(
            or_(
                OpsSection.owner_email == user.email,
                OpsSection.backup_email == user.email,
            )
        )
    )
    rows: dict[int, tuple[OpsSection, OpsService, str]] = {}
    for sec, svc in (await db.execute(owner_or_backup_stmt)).all():
        if sec.owner_email == user.email:
            rel = "owner"
        elif sec.backup_email == user.email:
            rel = "backup"
        else:
            continue
        rows[sec.id] = (sec, svc, rel)

    # 2) permission (user_id 기준) — 위와 중복되면 owner/backup 우선
    perm_stmt = (
        select(OpsSection, OpsService)
        .join(OpsService, OpsSection.service_id == OpsService.id)
        .join(OpsSectionPermission, OpsSectionPermission.section_id == OpsSection.id)
        .where(OpsSectionPermission.user_id == user.id)
    )
    for sec, svc in (await db.execute(perm_stmt)).all():
        rows.setdefault(sec.id, (sec, svc, "permission"))

    if not rows:
        return []

    # 3) 헬스 요약
    health_map = await summarize_for_sections(db, list(rows.keys()))

    out: list[MySectionDTO] = []
    for sid, (sec, svc, rel) in sorted(rows.items(), key=lambda x: (x[1][1].code, x[1][0].code)):
        out.append(
            MySectionDTO(
                section_id=sid,
                service_code=svc.code,
                service_display_name=svc.display_name,
                section_code=sec.code,
                section_name=sec.name,
                level=sec.level,
                status=sec.status,
                route=sec.route,
                relation=rel,
                health=health_map.get(sid),
            )
        )
    return out
