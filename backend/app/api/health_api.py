"""GET /api/health/snapshots/{service_code}/{section_code} — 시계열 + 요약."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dto import HealthSnapshotDTO, SectionHealthSummaryDTO
from app.core.security import get_current_user, require_role
from app.database.session import get_db
from app.jobs.health_probe import probe_all_sections
from app.models.health import OpsHealthSnapshot
from app.models.section import OpsSection
from app.models.service import OpsService
from app.models.user import OpsUser
from app.services.health_summary import summarize_for_sections

router = APIRouter(prefix="/health", tags=["health"])


async def _resolve_section_id(
    db: AsyncSession, service_code: str, section_code: str
) -> int:
    svc = (
        await db.execute(select(OpsService).where(OpsService.code == service_code))
    ).scalar_one_or_none()
    if svc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"service '{service_code}' 미등록")
    section = (
        await db.execute(
            select(OpsSection).where(
                OpsSection.service_id == svc.id, OpsSection.code == section_code
            )
        )
    ).scalar_one_or_none()
    if section is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"section '{section_code}' 미등록 in '{service_code}'",
        )
    return section.id


@router.get(
    "/snapshots/{service_code}/{section_code}",
    response_model=list[HealthSnapshotDTO],
)
async def list_snapshots(
    service_code: str,
    section_code: str,
    limit: int = Query(default=288, ge=1, le=2000),  # 24h * 12 (5분 주기)
    db: AsyncSession = Depends(get_db),
    _user: OpsUser = Depends(get_current_user),
) -> list[HealthSnapshotDTO]:
    section_id = await _resolve_section_id(db, service_code, section_code)
    rows = (
        await db.execute(
            select(OpsHealthSnapshot)
            .where(OpsHealthSnapshot.section_id == section_id)
            .order_by(OpsHealthSnapshot.checked_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return [HealthSnapshotDTO.model_validate(r) for r in rows]


@router.get(
    "/summary/{service_code}/{section_code}",
    response_model=SectionHealthSummaryDTO,
)
async def get_summary(
    service_code: str,
    section_code: str,
    db: AsyncSession = Depends(get_db),
    _user: OpsUser = Depends(get_current_user),
) -> SectionHealthSummaryDTO:
    section_id = await _resolve_section_id(db, service_code, section_code)
    summary_map = await summarize_for_sections(db, [section_id])
    return summary_map[section_id]


@router.post("/probe/run", response_model=dict)
async def trigger_probe(
    db: AsyncSession = Depends(get_db),
    _admin: OpsUser = Depends(require_role("ops_admin")),
) -> dict:
    """모든 섹션 즉시 점검 (수동 트리거) — ops_admin 만."""
    n = await probe_all_sections(db)
    return {"processed": n}
