"""5분 주기 헬스 점검 잡 — 매니페스트 health.url / health.api 호출 + 시계열 INSERT + 알림.

본 서비스 부하 회피:
- 동시성 제한 (Semaphore)
- 타임아웃 명시
- User-Agent 헤더로 운영 트래픽 식별
- 매니페스트의 health.url / health.api 둘 다 비어 있으면 스킵
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.jobs.url_guard import UnsafeURLError, assert_safe_probe_url
from app.manifest.parser import parse_manifest
from app.manifest.schema import Section as ManifestSection
from app.models.audit import OpsManifestSnapshot
from app.models.health import OpsHealthSnapshot
from app.models.section import OpsSection
from app.models.service import OpsService
from app.notify.alert_router import evaluate_and_notify

log = logging.getLogger("opsconsole.jobs.health_probe")


def _resolve_url(svc: OpsService, ms: ManifestSection) -> str | None:
    """헬스 점검 URL 결정. health.url 우선, 없으면 gateway_url + health.api 조합."""
    if ms.health is None:
        return None
    if ms.health.url:
        return str(ms.health.url)
    if ms.health.api and svc.gateway_url:
        base = str(svc.gateway_url).rstrip("/")
        path = ms.health.api if ms.health.api.startswith("/") else "/" + ms.health.api
        return base + path
    return None


def _build_section_index(manifest_dict: dict) -> dict[str, ManifestSection]:
    """raw manifest dict → {section_code: ManifestSection} 인덱스."""
    parsed = parse_manifest_from_dict(manifest_dict)
    return {s.code: s for s in parsed.sections}


def parse_manifest_from_dict(raw: dict):
    """이미 dict 인 매니페스트 → Manifest 모델 (yaml 파싱 생략)."""
    from app.manifest.schema import Manifest

    return Manifest.model_validate(raw)


async def _latest_manifest(db: AsyncSession, service_id: int) -> dict | None:
    snap = (
        await db.execute(
            select(OpsManifestSnapshot)
            .where(OpsManifestSnapshot.service_id == service_id)
            .order_by(OpsManifestSnapshot.fetched_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return snap.manifest if snap else None


async def _probe_one(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    url: str,
    method: str,
    expected_status: int,
    timeout_s: float,
) -> OpsHealthSnapshot:
    """단일 URL 점검 → snapshot row (section_id 미설정)."""
    async with sem:
        started = datetime.now(timezone.utc)
        try:
            res = await client.request(method, url, timeout=timeout_s)
            elapsed_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
            ok = res.status_code == expected_status
            return OpsHealthSnapshot(
                section_id=0,
                http_status=res.status_code,
                latency_ms=elapsed_ms,
                ok=ok,
                error_text=None if ok else f"expected {expected_status}, got {res.status_code}",
            )
        except (httpx.TimeoutException, httpx.RequestError) as e:
            elapsed_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
            return OpsHealthSnapshot(
                section_id=0,
                http_status=None,
                latency_ms=elapsed_ms,
                ok=False,
                error_text=f"{type(e).__name__}: {str(e)[:200]}",
            )


async def probe_all_sections(db: AsyncSession) -> int:
    """모든 등록 섹션을 한 번 점검. 처리한 섹션 수 반환."""
    # 1) 모든 (service, section) 페어 + 가장 최신 매니페스트 dict
    services = (await db.execute(select(OpsService))).scalars().all()
    if not services:
        return 0

    headers = {"User-Agent": settings.health_probe_user_agent, "Accept": "*/*"}
    sem = asyncio.Semaphore(settings.health_probe_concurrency)
    processed = 0

    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        for svc in services:
            manifest_dict = await _latest_manifest(db, svc.id)
            if manifest_dict is None:
                continue
            try:
                idx = _build_section_index(manifest_dict)
            except Exception as e:  # noqa: BLE001
                log.warning("[probe] manifest parse failed for %s: %s", svc.code, e)
                continue

            sections = (
                await db.execute(
                    select(OpsSection).where(OpsSection.service_id == svc.id)
                )
            ).scalars().all()

            tasks: list[tuple[OpsSection, ManifestSection, asyncio.Task]] = []
            for sec in sections:
                ms = idx.get(sec.code)
                if ms is None:
                    continue
                url = _resolve_url(svc, ms)
                if not url:
                    continue
                # SSRF 방어 — 사설 IP / 잘못된 스킴 차단
                try:
                    assert_safe_probe_url(url)
                except UnsafeURLError as e:
                    snap = OpsHealthSnapshot(
                        section_id=sec.id,
                        http_status=None,
                        latency_ms=0,
                        ok=False,
                        error_text=f"unsafe url: {e}",
                    )
                    db.add(snap)
                    await db.flush()
                    await evaluate_and_notify(db, svc, sec, snap)
                    processed += 1
                    log.warning("[probe] unsafe url skipped %s/%s: %s", svc.code, sec.code, e)
                    continue
                method = ms.health.method if ms.health else "GET"
                expected = ms.health.expected_status if ms.health else 200
                timeout = (
                    (ms.health.timeout_ms / 1000.0)
                    if ms.health and ms.health.timeout_ms
                    else settings.health_probe_timeout_s
                )
                tasks.append(
                    (
                        sec,
                        ms,
                        asyncio.create_task(
                            _probe_one(client, sem, url, method, expected, timeout)
                        ),
                    )
                )

            for sec, ms, task in tasks:
                snap = await task
                snap.section_id = sec.id
                db.add(snap)
                await db.flush()  # snap.id 확보
                await evaluate_and_notify(db, svc, sec, snap)
                processed += 1

    await db.commit()
    log.info("[probe] processed %d sections", processed)
    return processed


async def run_probe_with_own_engine() -> int:
    """APScheduler 가 호출 — 자체 engine/session 으로 1회 실행."""
    if not settings.health_probe_enabled:
        return 0
    engine = create_async_engine(settings.database_url, echo=False)
    Session = async_sessionmaker(bind=engine, expire_on_commit=False)
    try:
        async with Session() as session:
            return await probe_all_sections(session)
    finally:
        await engine.dispose()
