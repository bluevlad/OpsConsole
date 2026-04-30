"""Slack 라우터 + 디듀프 단위 테스트 (실 Slack 호출은 모킹)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.manifest.parser import parse_manifest
from app.manifest.sync import upsert_catalog
from app.models.health import OpsAlertState, OpsHealthSnapshot
from app.models.section import OpsSection
from app.models.service import OpsService
from app.notify import alert_router
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "allergyinsight-manifest.yml"


async def _seed(db_session: AsyncSession) -> tuple[OpsService, OpsSection]:
    text = FIXTURE.read_text(encoding="utf-8")
    manifest = parse_manifest(text)
    await upsert_catalog(db_session, manifest, ref="test")
    svc = (
        await db_session.execute(select(OpsService).where(OpsService.code == "allergyinsight"))
    ).scalar_one()
    sec = (
        await db_session.execute(
            select(OpsSection).where(
                OpsSection.service_id == svc.id, OpsSection.code == "ai-consult"
            )
        )
    ).scalar_one()
    return svc, sec


def _snap(ok: bool, status: int = 200, lat: int = 100, err: str | None = None) -> OpsHealthSnapshot:
    return OpsHealthSnapshot(
        section_id=0, http_status=status, latency_ms=lat, ok=ok, error_text=err
    )


@pytest.mark.asyncio
async def test_three_consecutive_failures_triggers_alert(db_session: AsyncSession):
    svc, sec = await _seed(db_session)

    fake_send = AsyncMock(return_value=True)
    with patch("app.notify.alert_router.send_to_slack", fake_send):
        # 1, 2회 — noop
        for _ in range(2):
            r = await alert_router.evaluate_and_notify(
                db_session, svc, sec, _snap(False, 503, err="boom")
            )
            assert r == "noop"
        assert fake_send.await_count == 0

        # 3회 — alert
        r = await alert_router.evaluate_and_notify(
            db_session, svc, sec, _snap(False, 503, err="boom")
        )
        assert r == "failure_alert"
        assert fake_send.await_count == 1

    state = (
        await db_session.execute(
            select(OpsAlertState).where(OpsAlertState.section_id == sec.id)
        )
    ).scalar_one()
    assert state.consecutive_failures == 3
    assert state.resolved_notified is False
    assert state.last_alerted_at is not None


@pytest.mark.asyncio
async def test_cooldown_suppresses_repeat_alert(db_session: AsyncSession):
    svc, sec = await _seed(db_session)
    base = datetime(2026, 4, 30, 12, 0, 0, tzinfo=timezone.utc)

    fake_send = AsyncMock(return_value=True)
    with patch("app.notify.alert_router.send_to_slack", fake_send):
        # 3회 실패 → 알림 발송
        for i in range(3):
            await alert_router.evaluate_and_notify(
                db_session, svc, sec, _snap(False, 503), now=base + timedelta(seconds=i)
            )
        assert fake_send.await_count == 1

        # 30분 후 추가 실패 — cooldown 중이므로 무시
        r = await alert_router.evaluate_and_notify(
            db_session, svc, sec, _snap(False, 503), now=base + timedelta(minutes=30)
        )
        assert r == "cooldown"
        assert fake_send.await_count == 1

        # 1시간 1분 후 — cooldown 만료, 재알림
        r = await alert_router.evaluate_and_notify(
            db_session,
            svc,
            sec,
            _snap(False, 503),
            now=base + timedelta(hours=1, minutes=1),
        )
        assert r == "failure_alert"
        assert fake_send.await_count == 2


@pytest.mark.asyncio
async def test_recovery_sends_one_alert_then_silent(db_session: AsyncSession):
    svc, sec = await _seed(db_session)

    fake_send = AsyncMock(return_value=True)
    with patch("app.notify.alert_router.send_to_slack", fake_send):
        # 3회 실패 → 알림
        for _ in range(3):
            await alert_router.evaluate_and_notify(
                db_session, svc, sec, _snap(False, 503)
            )

        # 회복 — 1회 알림
        r = await alert_router.evaluate_and_notify(
            db_session, svc, sec, _snap(True, 200, 50)
        )
        assert r == "recovered_alert"
        assert fake_send.await_count == 2  # failure + recovered

        # 정상 상태 유지 — noop
        for _ in range(3):
            r = await alert_router.evaluate_and_notify(
                db_session, svc, sec, _snap(True, 200, 50)
            )
            assert r == "noop"
        assert fake_send.await_count == 2  # 그대로

    state = (
        await db_session.execute(
            select(OpsAlertState).where(OpsAlertState.section_id == sec.id)
        )
    ).scalar_one()
    assert state.consecutive_failures == 0
    assert state.resolved_notified is True


@pytest.mark.asyncio
async def test_first_event_below_threshold_no_alert(db_session: AsyncSession):
    """초기 상태에서 단일 실패는 알림 없음 (threshold=3)."""
    svc, sec = await _seed(db_session)
    fake_send = AsyncMock(return_value=True)
    with patch("app.notify.alert_router.send_to_slack", fake_send):
        r = await alert_router.evaluate_and_notify(
            db_session, svc, sec, _snap(False, 500)
        )
    assert r == "noop"
    assert fake_send.await_count == 0


@pytest.mark.asyncio
async def test_initial_ok_no_recovery_alert(db_session: AsyncSession):
    """처음부터 정상이면 회복 알림 없음 (resolved_notified 초기값 True)."""
    svc, sec = await _seed(db_session)
    fake_send = AsyncMock(return_value=True)
    with patch("app.notify.alert_router.send_to_slack", fake_send):
        r = await alert_router.evaluate_and_notify(
            db_session, svc, sec, _snap(True, 200, 50)
        )
    assert r == "noop"
    assert fake_send.await_count == 0
