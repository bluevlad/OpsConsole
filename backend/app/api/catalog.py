"""GET /api/catalog/services, /sections + POST /sync — 카탈로그 read-only + sync."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dto import (
    SectionAssetDTO,
    SectionDTO,
    ServiceDTO,
    SyncRequest,
    SyncResponseDTO,
)
from app.database.session import get_db
from app.manifest import fetcher
from app.manifest.parser import ManifestParseError, parse_manifest
from app.manifest.sync import upsert_catalog
from app.models.section import OpsSection, OpsSectionAsset
from app.models.service import OpsService
from app.services.health_summary import summarize_for_sections

router = APIRouter(prefix="/catalog", tags=["catalog"])


# -- GET /catalog/services -------------------------------------------------


@router.get("/services", response_model=list[ServiceDTO])
async def list_services(db: AsyncSession = Depends(get_db)) -> list[ServiceDTO]:
    """등록된 서비스 + 섹션 수."""
    section_count_subq = (
        select(OpsSection.service_id, func.count(OpsSection.id).label("cnt"))
        .group_by(OpsSection.service_id)
        .subquery()
    )
    stmt = (
        select(OpsService, func.coalesce(section_count_subq.c.cnt, 0))
        .outerjoin(section_count_subq, OpsService.id == section_count_subq.c.service_id)
        .order_by(OpsService.code)
    )
    rows = (await db.execute(stmt)).all()
    return [
        ServiceDTO.model_validate({**svc.__dict__, "section_count": cnt})
        for svc, cnt in rows
    ]


@router.get("/services/{code}", response_model=ServiceDTO)
async def get_service(code: str, db: AsyncSession = Depends(get_db)) -> ServiceDTO:
    svc = (
        await db.execute(select(OpsService).where(OpsService.code == code))
    ).scalar_one_or_none()
    if svc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"service '{code}' 미등록")
    cnt = (
        await db.execute(
            select(func.count(OpsSection.id)).where(OpsSection.service_id == svc.id)
        )
    ).scalar_one()
    return ServiceDTO.model_validate({**svc.__dict__, "section_count": cnt})


# -- GET /catalog/services/{code}/sections ---------------------------------


@router.get("/services/{code}/sections", response_model=list[SectionDTO])
async def list_sections(
    code: str, db: AsyncSession = Depends(get_db)
) -> list[SectionDTO]:
    svc = (
        await db.execute(select(OpsService).where(OpsService.code == code))
    ).scalar_one_or_none()
    if svc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"service '{code}' 미등록")

    sections = (
        await db.execute(
            select(OpsSection)
            .where(OpsSection.service_id == svc.id)
            .order_by(OpsSection.code)
        )
    ).scalars().all()

    section_ids = [s.id for s in sections]
    if section_ids:
        assets_rows = (
            await db.execute(
                select(OpsSectionAsset).where(
                    OpsSectionAsset.section_id.in_(section_ids)
                )
            )
        ).scalars().all()
    else:
        assets_rows = []

    by_section: dict[int, list[OpsSectionAsset]] = {}
    for a in assets_rows:
        by_section.setdefault(a.section_id, []).append(a)

    health_map = await summarize_for_sections(db, section_ids)

    result: list[SectionDTO] = []
    for s in sections:
        result.append(
            SectionDTO.model_validate(
                {
                    **s.__dict__,
                    "assets": [
                        SectionAssetDTO.model_validate(a) for a in by_section.get(s.id, [])
                    ],
                    "health": health_map.get(s.id),
                }
            )
        )
    return result


@router.get(
    "/services/{code}/sections/{section_code}", response_model=SectionDTO
)
async def get_section(
    code: str, section_code: str, db: AsyncSession = Depends(get_db)
) -> SectionDTO:
    svc = (
        await db.execute(select(OpsService).where(OpsService.code == code))
    ).scalar_one_or_none()
    if svc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"service '{code}' 미등록")

    section = (
        await db.execute(
            select(OpsSection).where(
                OpsSection.service_id == svc.id, OpsSection.code == section_code
            )
        )
    ).scalar_one_or_none()
    if section is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"section '{section_code}' 미등록 in '{code}'"
        )

    assets = (
        await db.execute(
            select(OpsSectionAsset).where(OpsSectionAsset.section_id == section.id)
        )
    ).scalars().all()

    health_map = await summarize_for_sections(db, [section.id])

    return SectionDTO.model_validate(
        {
            **section.__dict__,
            "assets": [SectionAssetDTO.model_validate(a) for a in assets],
            "health": health_map.get(section.id),
        }
    )


# -- POST /catalog/sync ----------------------------------------------------


@router.post("/sync", response_model=SyncResponseDTO)
async def sync_catalog(
    req: SyncRequest, db: AsyncSession = Depends(get_db)
) -> SyncResponseDTO:
    """매니페스트를 가져와 카탈로그에 반영한다.

    P0: 인증 미적용 (P5에서 ops_admin 권한 게이트 추가 예정).
    """
    # 1) 매니페스트 텍스트 확보
    try:
        if req.mode == "github":
            if not req.repo_url:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    "mode='github' 일 때 repo_url 필수",
                )
            text = await fetcher.fetch_from_github(req.repo_url, ref=req.ref)
        elif req.mode == "local":
            if not req.local_path:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    "mode='local' 일 때 local_path 필수",
                )
            text = fetcher.fetch_local_fallback(req.local_path)
        elif req.mode == "inline":
            if not req.manifest_yaml:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    "mode='inline' 일 때 manifest_yaml 필수",
                )
            text = req.manifest_yaml
        else:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, f"알 수 없는 mode: {req.mode}"
            )
    except fetcher.ManifestFetchError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from e

    # 2) 파싱 + 검증
    try:
        manifest = parse_manifest(text)
    except ManifestParseError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    # 3) service_code 일치 확인
    if manifest.service != req.service_code:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"매니페스트 service ('{manifest.service}') != 요청 service_code ('{req.service_code}')",
        )

    # 4) sync 실행 + commit
    report = await upsert_catalog(db, manifest, ref=req.ref)
    await db.commit()

    return SyncResponseDTO(
        service_code=report.service_code,
        created=report.created,
        sections_added=report.sections_added,
        sections_updated=report.sections_updated,
        sections_deleted=report.sections_deleted,
        snapshot_id=report.snapshot_id,
        total_changes=report.total_changes,
    )
