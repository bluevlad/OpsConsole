"""검증된 Manifest 모델을 DB에 upsert.

처리:
1. ops_services upsert (code 기준)
2. ops_sections diff: 매니페스트에 있으면 upsert, DB에만 있으면 삭제 (CASCADE로 assets도 정리)
3. ops_section_assets 전체 교체 (각 섹션별 delete-then-insert)
4. ops_manifest_snapshots 추가 (감사용 raw 저장)
5. ops_audit_log 'sync_manifest' 1건 기록

원자성: 단일 트랜잭션 (예외 시 전체 rollback).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.manifest.schema import Manifest, Section
from app.models.audit import OpsAuditLog, OpsManifestSnapshot
from app.models.section import OpsSection, OpsSectionAsset
from app.models.service import OpsService


@dataclass
class SyncReport:
    """sync 결과 요약 — UI/CLI 출력용."""

    service_code: str
    created: bool                      # ops_services 신규 생성 여부
    sections_added: list[str] = field(default_factory=list)
    sections_updated: list[str] = field(default_factory=list)
    sections_deleted: list[str] = field(default_factory=list)
    snapshot_id: int | None = None

    @property
    def total_changes(self) -> int:
        return (
            len(self.sections_added)
            + len(self.sections_updated)
            + len(self.sections_deleted)
        )


# -- 헬퍼 --------------------------------------------------------------------


def _section_to_assets(section: Section, section_id: int) -> list[OpsSectionAsset]:
    """Section.assets → ops_section_assets 행 리스트로 분해."""
    rows: list[OpsSectionAsset] = []
    asset_groups = (
        ("frontend", section.assets.frontend),
        ("backend_router", section.assets.backend_router),
        ("service", section.assets.service),
        ("model", section.assets.models),
        ("table", section.assets.tables),
        ("endpoint", section.assets.endpoints),
    )
    for asset_type, paths in asset_groups:
        for path in paths:
            rows.append(
                OpsSectionAsset(
                    section_id=section_id,
                    asset_type=asset_type,
                    path=path,
                )
            )
    return rows


async def _upsert_service(session: AsyncSession, manifest: Manifest) -> tuple[OpsService, bool]:
    """ops_services row 조회·생성. (row, created) 반환."""
    stmt = select(OpsService).where(OpsService.code == manifest.service)
    existing = (await session.execute(stmt)).scalar_one_or_none()

    if existing is None:
        new = OpsService(
            code=manifest.service,
            display_name=manifest.display_name,
            gateway_url=str(manifest.gateway_url) if manifest.gateway_url else None,
            repo_url=str(manifest.repo_url) if manifest.repo_url else None,
            last_synced_at=datetime.now(timezone.utc),
        )
        session.add(new)
        await session.flush()  # id 확보
        return new, True

    existing.display_name = manifest.display_name
    if manifest.gateway_url is not None:
        existing.gateway_url = str(manifest.gateway_url)
    if manifest.repo_url is not None:
        existing.repo_url = str(manifest.repo_url)
    existing.last_synced_at = datetime.now(timezone.utc)
    return existing, False


async def _diff_and_apply_sections(
    session: AsyncSession,
    service: OpsService,
    manifest: Manifest,
    report: SyncReport,
) -> None:
    """ops_sections + ops_section_assets diff·apply."""
    # 현재 DB 섹션
    db_sections_stmt = select(OpsSection).where(OpsSection.service_id == service.id)
    db_sections = (await session.execute(db_sections_stmt)).scalars().all()
    db_by_code: dict[str, OpsSection] = {s.code: s for s in db_sections}

    manifest_codes = {s.code for s in manifest.sections}

    # 1) 삭제: 매니페스트에서 사라진 섹션
    for code, db_row in db_by_code.items():
        if code not in manifest_codes:
            await session.delete(db_row)  # CASCADE로 assets도 자동 삭제
            report.sections_deleted.append(code)

    # 2) 추가/갱신
    for section in manifest.sections:
        existing = db_by_code.get(section.code)
        if existing is None:
            new = OpsSection(
                service_id=service.id,
                code=section.code,
                name=section.name,
                level=section.level,
                route=section.route,
                owner_email=section.owner,
                backup_email=section.backup,
                status=section.status,
            )
            session.add(new)
            await session.flush()  # id 확보
            for asset in _section_to_assets(section, new.id):
                session.add(asset)
            report.sections_added.append(section.code)
        else:
            existing.name = section.name
            existing.level = section.level
            existing.route = section.route
            existing.owner_email = section.owner
            existing.backup_email = section.backup
            existing.status = section.status
            # 자산은 항상 전량 교체 (diff가 단순)
            await session.execute(
                delete(OpsSectionAsset).where(OpsSectionAsset.section_id == existing.id)
            )
            for asset in _section_to_assets(section, existing.id):
                session.add(asset)
            report.sections_updated.append(section.code)


# -- 공개 API ---------------------------------------------------------------


async def upsert_catalog(
    session: AsyncSession,
    manifest: Manifest,
    *,
    raw_manifest: dict[str, Any] | None = None,
    ref: str = "main",
    actor_id: int | None = None,
) -> SyncReport:
    """매니페스트 1건을 카탈로그에 반영한다 (단일 트랜잭션 가정).

    Args:
        session: 호출자가 트랜잭션 경계를 관리. 함수 내부에서 commit 안 함.
        manifest: 검증된 Manifest 모델.
        raw_manifest: ops_manifest_snapshots에 저장할 원본 dict.
            None이면 manifest.model_dump(mode='json') 사용.
        ref: git ref (snapshot에 기록).
        actor_id: 감사 로그 actor (None이면 system sync).
    """
    service, created = await _upsert_service(session, manifest)
    report = SyncReport(service_code=service.code, created=created)

    await _diff_and_apply_sections(session, service, manifest, report)

    snapshot = OpsManifestSnapshot(
        service_id=service.id,
        ref=ref,
        manifest=raw_manifest or manifest.model_dump(mode="json"),
    )
    session.add(snapshot)
    await session.flush()
    report.snapshot_id = snapshot.id

    audit = OpsAuditLog(
        actor_id=actor_id,
        action="sync_manifest",
        target_type="ops_services",
        target_id=str(service.id),
        payload={
            "service_code": service.code,
            "ref": ref,
            "created": created,
            "added": report.sections_added,
            "updated": report.sections_updated,
            "deleted": report.sections_deleted,
        },
    )
    session.add(audit)
    await session.flush()

    return report
