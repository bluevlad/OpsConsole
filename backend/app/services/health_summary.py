"""헬스 시계열 → 섹션별 요약 (last + 24h availability)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dto import SectionHealthSummaryDTO
from app.models.health import OpsHealthSnapshot


async def summarize_for_sections(
    db: AsyncSession, section_ids: list[int]
) -> dict[int, SectionHealthSummaryDTO]:
    """섹션 id 리스트 → 각 섹션의 최근 1건 + 24h 가용률.

    빈 리스트면 빈 dict. 섹션이 시계열을 갖지 않아도 dict 키엔 포함되며 모든 값 None/0.
    """
    if not section_ids:
        return {}

    summaries: dict[int, SectionHealthSummaryDTO] = {
        sid: SectionHealthSummaryDTO(section_id=sid) for sid in section_ids
    }

    # 1) 24h 가용률 + 샘플 수
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    ok_count = func.sum(case((OpsHealthSnapshot.ok.is_(True), 1), else_=0))
    total_count = func.count(OpsHealthSnapshot.id)
    avail_stmt = (
        select(
            OpsHealthSnapshot.section_id,
            ok_count.label("ok_n"),
            total_count.label("total_n"),
        )
        .where(
            OpsHealthSnapshot.section_id.in_(section_ids),
            OpsHealthSnapshot.checked_at >= cutoff,
        )
        .group_by(OpsHealthSnapshot.section_id)
    )
    for row in (await db.execute(avail_stmt)).all():
        s = summaries[row.section_id]
        s.samples_24h = int(row.total_n)
        s.availability_24h = (row.ok_n / row.total_n) if row.total_n else None

    # 2) 가장 최근 스냅샷 1건씩
    sub = (
        select(
            OpsHealthSnapshot,
            func.row_number()
            .over(
                partition_by=OpsHealthSnapshot.section_id,
                order_by=OpsHealthSnapshot.checked_at.desc(),
            )
            .label("rn"),
        )
        .where(OpsHealthSnapshot.section_id.in_(section_ids))
        .subquery()
    )
    latest_stmt = select(sub).where(sub.c.rn == 1)
    for row in (await db.execute(latest_stmt)).all():
        s = summaries[row.section_id]
        s.last_checked_at = row.checked_at
        s.last_ok = row.ok
        s.last_status = row.http_status
        s.last_latency_ms = row.latency_ms

    return summaries
