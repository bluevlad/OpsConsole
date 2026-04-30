"""APScheduler 부트스트랩 — FastAPI lifespan 에서 시작/종료."""
from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import settings
from app.jobs.health_probe import run_probe_with_own_engine

log = logging.getLogger("opsconsole.jobs.scheduler")

_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler | None:
    return _scheduler


def start_scheduler() -> AsyncIOScheduler | None:
    """FastAPI 시작 시 호출. health_probe_enabled=false 면 None 반환 (no-op)."""
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    if not settings.health_probe_enabled:
        log.info("[scheduler] health_probe disabled, skipping")
        return None

    _scheduler = AsyncIOScheduler(timezone=settings.app_tz)
    _scheduler.add_job(
        run_probe_with_own_engine,
        trigger=IntervalTrigger(minutes=settings.health_probe_interval_minutes),
        id="health_probe",
        next_run_time=None,  # 첫 실행은 5분 후 — 부팅 직후 cold-start 방지
        max_instances=1,
        coalesce=True,
    )
    _scheduler.start()
    log.info(
        "[scheduler] started — health_probe every %d min",
        settings.health_probe_interval_minutes,
    )
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        log.info("[scheduler] stopped")
