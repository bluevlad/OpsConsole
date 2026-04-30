"""manifest sync — opsconsole_dev DB에 실제 upsert/diff 검증 (rollback 격리)."""
from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.manifest.parser import parse_manifest
from app.manifest.schema import Manifest
from app.manifest.sync import upsert_catalog
from app.models.audit import OpsAuditLog, OpsManifestSnapshot
from app.models.section import OpsSection, OpsSectionAsset
from app.models.service import OpsService

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _load_seed() -> Manifest:
    return parse_manifest((FIXTURE_DIR / "allergyinsight-manifest.yml").read_text())


def _minimal_manifest(service: str = "demo") -> Manifest:
    return Manifest.model_validate(
        {
            "version": "1.0",
            "service": service,
            "display_name": service.capitalize(),
            "sections": [
                {
                    "code": "alpha",
                    "name": "Alpha",
                    "level": "public",
                    "owner": "owner@example.com",
                    "assets": {"frontend": ["src/A.jsx"], "tables": ["t1"]},
                },
                {"code": "beta", "name": "Beta", "level": "admin"},
            ],
        }
    )


# -- 신규 등록 --------------------------------------------------------------


@pytest.mark.asyncio
async def test_upsert_creates_new_service_and_sections(db_session: AsyncSession):
    manifest = _minimal_manifest("demo")
    report = await upsert_catalog(db_session, manifest, ref="main")

    assert report.created is True
    assert sorted(report.sections_added) == ["alpha", "beta"]
    assert report.sections_updated == []
    assert report.sections_deleted == []

    svc = (
        await db_session.execute(select(OpsService).where(OpsService.code == "demo"))
    ).scalar_one()
    assert svc.display_name == "Demo"

    sections = (
        await db_session.execute(
            select(OpsSection).where(OpsSection.service_id == svc.id).order_by(OpsSection.code)
        )
    ).scalars().all()
    assert [s.code for s in sections] == ["alpha", "beta"]
    assert sections[0].owner_email == "owner@example.com"

    # alpha 자산: frontend 1 + table 1 = 2 행
    assets = (
        await db_session.execute(
            select(OpsSectionAsset).where(OpsSectionAsset.section_id == sections[0].id)
        )
    ).scalars().all()
    assert len(assets) == 2
    types = {a.asset_type for a in assets}
    assert types == {"frontend", "table"}


# -- diff: 추가 / 갱신 / 삭제 -----------------------------------------------


@pytest.mark.asyncio
async def test_upsert_diff_adds_updates_deletes(db_session: AsyncSession):
    # 1차 sync
    await upsert_catalog(db_session, _minimal_manifest("demo"), ref="main")

    # 2차 매니페스트: alpha 갱신, beta 삭제, gamma 추가
    second = Manifest.model_validate(
        {
            "version": "1.0",
            "service": "demo",
            "display_name": "Demo (renamed)",
            "sections": [
                {
                    "code": "alpha",
                    "name": "Alpha v2",
                    "level": "member",  # public → member
                    "assets": {"frontend": ["src/A2.jsx"]},
                },
                {"code": "gamma", "name": "Gamma", "level": "public"},
            ],
        }
    )

    report = await upsert_catalog(db_session, second, ref="main")
    assert report.created is False
    assert report.sections_added == ["gamma"]
    assert report.sections_updated == ["alpha"]
    assert report.sections_deleted == ["beta"]

    svc = (
        await db_session.execute(select(OpsService).where(OpsService.code == "demo"))
    ).scalar_one()
    assert svc.display_name == "Demo (renamed)"

    sections = (
        await db_session.execute(
            select(OpsSection).where(OpsSection.service_id == svc.id).order_by(OpsSection.code)
        )
    ).scalars().all()
    assert [s.code for s in sections] == ["alpha", "gamma"]
    alpha = next(s for s in sections if s.code == "alpha")
    assert alpha.level == "member"
    assert alpha.name == "Alpha v2"

    # alpha 자산은 전량 교체 — 새 frontend 1건만
    assets = (
        await db_session.execute(
            select(OpsSectionAsset).where(OpsSectionAsset.section_id == alpha.id)
        )
    ).scalars().all()
    assert [(a.asset_type, a.path) for a in assets] == [("frontend", "src/A2.jsx")]


# -- snapshot + audit log ---------------------------------------------------


@pytest.mark.asyncio
async def test_upsert_records_snapshot_and_audit(db_session: AsyncSession):
    manifest = _minimal_manifest("demo")
    report = await upsert_catalog(db_session, manifest, ref="abc1234", actor_id=None)

    assert report.snapshot_id is not None

    snap = (
        await db_session.execute(
            select(OpsManifestSnapshot).where(OpsManifestSnapshot.id == report.snapshot_id)
        )
    ).scalar_one()
    assert snap.ref == "abc1234"
    assert snap.manifest["service"] == "demo"

    audit = (
        await db_session.execute(
            select(OpsAuditLog)
            .where(OpsAuditLog.action == "sync_manifest")
            .order_by(OpsAuditLog.id.desc())
            .limit(1)
        )
    ).scalar_one()
    assert audit.target_type == "ops_services"
    assert audit.payload["service_code"] == "demo"
    assert audit.payload["created"] is True


# -- 1호 고객 시드: 11섹션 ---------------------------------------------------


@pytest.mark.asyncio
async def test_upsert_allergyinsight_seed_creates_11_sections(db_session: AsyncSession):
    manifest = _load_seed()
    report = await upsert_catalog(db_session, manifest, ref="prod")

    assert report.created is True
    assert len(report.sections_added) == 11

    svc = (
        await db_session.execute(select(OpsService).where(OpsService.code == "allergyinsight"))
    ).scalar_one()

    section_codes = (
        await db_session.execute(
            select(OpsSection.code).where(OpsSection.service_id == svc.id).order_by(OpsSection.code)
        )
    ).scalars().all()
    assert len(section_codes) == 11
    assert "ai-consult" in section_codes
    assert "drug-management" in section_codes

    # ai-consult 자산 — frontend 1 + backend_router 1 + service 1 + table 2 + endpoint 3 = 8
    ai_consult = (
        await db_session.execute(
            select(OpsSection).where(
                OpsSection.service_id == svc.id, OpsSection.code == "ai-consult"
            )
        )
    ).scalar_one()
    asset_count = len(
        (
            await db_session.execute(
                select(OpsSectionAsset).where(OpsSectionAsset.section_id == ai_consult.id)
            )
        ).scalars().all()
    )
    assert asset_count == 8
