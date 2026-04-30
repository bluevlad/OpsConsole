"""헬스 결과 → Slack 알림 라우팅 + 디듀프 정책.

규칙:
- 연속 실패 3회 도달 시 1회 알림 발송 (이후 cooldown 1h 동안 재발송 안 함)
- 실패 → 회복 시 1회 'recovered' 알림 (resolved_notified=True 토글)
- ops_alert_state row 가 없으면 자동 생성

호출 시점: 매 헬스 스냅샷 INSERT 직후 (session 안에서). commit 은 호출자가.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.health import OpsAlertState, OpsHealthSnapshot
from app.models.section import OpsSection
from app.models.service import OpsService
from app.notify.slack import send_to_slack

# 정책 파라미터 — 환경 변수로 빼지 않고 상수 (운영 단계에서 .env 추가 가능)
FAILURE_THRESHOLD = 3
COOLDOWN = timedelta(hours=1)


async def _get_or_create_state(db: AsyncSession, section_id: int) -> OpsAlertState:
    state = (
        await db.execute(
            select(OpsAlertState).where(OpsAlertState.section_id == section_id)
        )
    ).scalar_one_or_none()
    if state is None:
        state = OpsAlertState(
            section_id=section_id,
            consecutive_failures=0,
            resolved_notified=True,  # 초기엔 '정상'으로 간주 — 첫 실패가 곧 알림 트리거
        )
        db.add(state)
        await db.flush()
    return state


def _format_failure_text(svc: OpsService, sec: OpsSection, snap: OpsHealthSnapshot) -> str:
    parts = [
        f":rotating_light: *{svc.display_name} / {sec.name}* health check 실패",
        f"• section: `{svc.code}/{sec.code}`",
        f"• status: `{snap.http_status}`  latency: `{snap.latency_ms}ms`",
    ]
    if snap.error_text:
        parts.append(f"• error: `{snap.error_text[:200]}`")
    if sec.owner_email:
        parts.append(f"• owner: {sec.owner_email}")
    if sec.backup_email:
        parts.append(f"• backup: {sec.backup_email}")
    return "\n".join(parts)


def _format_recovered_text(svc: OpsService, sec: OpsSection, snap: OpsHealthSnapshot) -> str:
    return (
        f":white_check_mark: *{svc.display_name} / {sec.name}* 복구됨 — "
        f"status `{snap.http_status}` ({snap.latency_ms}ms)"
    )


async def evaluate_and_notify(
    db: AsyncSession,
    service: OpsService,
    section: OpsSection,
    snapshot: OpsHealthSnapshot,
    *,
    now: datetime | None = None,
) -> str:
    """스냅샷 결과로 알림 상태 갱신·발송 결정. 실제 작업 결과 라벨 반환.

    반환값: 'failure_alert' / 'recovered_alert' / 'cooldown' / 'noop'
    """
    state = await _get_or_create_state(db, section.id)
    now_ts = now or datetime.now(timezone.utc)

    if not snapshot.ok:
        state.consecutive_failures += 1
        # 임계 도달 + cooldown 외부일 때만 발송
        if state.consecutive_failures >= FAILURE_THRESHOLD:
            in_cooldown = (
                state.last_alerted_at is not None
                and (now_ts - state.last_alerted_at) < COOLDOWN
            )
            if in_cooldown:
                return "cooldown"
            await send_to_slack(_format_failure_text(service, section, snapshot))
            state.last_alerted_at = now_ts
            state.resolved_notified = False
            return "failure_alert"
        return "noop"

    # ok=True (회복 또는 정상 유지)
    was_failing = state.consecutive_failures > 0 or not state.resolved_notified
    state.consecutive_failures = 0
    if was_failing and not state.resolved_notified:
        await send_to_slack(_format_recovered_text(service, section, snapshot))
        state.resolved_notified = True
        return "recovered_alert"
    return "noop"
