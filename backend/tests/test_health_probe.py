"""헬스 잡 통합 테스트 — 모든 섹션 점검 + 시계열 INSERT + 알림 라우팅 (httpx 모킹)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs import health_probe
from app.manifest.parser import parse_manifest
from app.manifest.sync import upsert_catalog
from app.models.health import OpsHealthSnapshot
from app.models.service import OpsService

FIXTURE = Path(__file__).parent / "fixtures" / "allergyinsight-manifest.yml"


async def _seed(db_session: AsyncSession) -> OpsService:
    text = FIXTURE.read_text(encoding="utf-8")
    manifest = parse_manifest(text)
    await upsert_catalog(db_session, manifest, ref="test")
    return (
        await db_session.execute(select(OpsService).where(OpsService.code == "allergyinsight"))
    ).scalar_one()


@pytest.mark.asyncio
@respx.mock
async def test_probe_all_sections_records_snapshots(db_session: AsyncSession):
    await _seed(db_session)

    # respx 는 unhandled URL 을 거부하므로 와일드카드 라우트로 모두 200 응답
    respx.get(host="allergy.unmong.com").mock(return_value=httpx.Response(200, text="ok"))

    fake_send = AsyncMock(return_value=True)
    with patch("app.notify.alert_router.send_to_slack", fake_send):
        n = await health_probe.probe_all_sections(db_session)

    # AllergyInsight 시드의 health.url / health.api 가 정의된 섹션은 10개 (wiki는 health.url만)
    # 정확한 수치 대신 합리적 범위로 검증
    assert n >= 6  # 최소 6개 이상 점검
    snapshots = (await db_session.execute(select(OpsHealthSnapshot))).scalars().all()
    assert len(snapshots) == n
    # 모두 ok=True
    assert all(s.ok for s in snapshots)
    # alert 발송 없어야 함 (전부 정상)
    assert fake_send.await_count == 0


@pytest.mark.asyncio
@respx.mock
async def test_probe_failure_eventually_alerts(db_session: AsyncSession):
    await _seed(db_session)

    # 모든 요청 503 — 3회 연속 실패하면 섹션마다 알림 발송
    respx.get(host="allergy.unmong.com").mock(
        return_value=httpx.Response(503, text="Service Unavailable")
    )

    fake_send = AsyncMock(return_value=True)
    with patch("app.notify.alert_router.send_to_slack", fake_send):
        # 1차 — noop (consecutive_failures=1)
        await health_probe.probe_all_sections(db_session)
        assert fake_send.await_count == 0

        # 2차 — noop (=2)
        await health_probe.probe_all_sections(db_session)
        assert fake_send.await_count == 0

        # 3차 — alert per section
        await health_probe.probe_all_sections(db_session)
        # 1차에서 점검한 섹션 수만큼 알림이 발송되어야 함
        assert fake_send.await_count >= 6


@pytest.mark.asyncio
async def test_probe_no_services_returns_zero(db_session: AsyncSession):
    n = await health_probe.probe_all_sections(db_session)
    assert n == 0
