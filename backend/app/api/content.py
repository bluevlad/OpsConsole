"""콘텐츠 블록 CRUD + 워크플로 (P3).

라우트:
  GET    /api/content/sections/{service_code}/{section_code}/blocks
  GET    /api/content/blocks/{block_id}
  PUT    /api/content/blocks/{block_id}/draft           edit (can_edit_content)
  POST   /api/content/blocks/{block_id}/request-review  → pending_review
  POST   /api/content/blocks/{block_id}/approve         (reviewer or ops_admin)
  POST   /api/content/blocks/{block_id}/reject          (reviewer or ops_admin)
  POST   /api/content/blocks/{block_id}/publish         (can_publish or ops_admin)
  GET    /api/content/blocks/{block_id}/versions

권한 모델:
- 모든 인증 사용자 read
- can_edit_content (또는 ops_admin) → draft 편집·검토 요청
- can_publish (또는 ops_admin) → 승인/게시
- 검토자 1차 자기 자신 승인 가능 — 단순화 (운영 단계엔 분리 가능)
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dto import (
    ContentBlockDTO,
    ContentBlockListItemDTO,
    ContentBlockSpecDTO,
    DraftSaveRequest,
    ReviewDecisionRequest,
    ReviewRequest,
)
from app.content.publisher import publish_block
from app.content.validator import (
    ContentBlockSpec,
    ContentValidationError,
    assert_writable,
    fetch_block_spec,
)
from app.core.security import get_current_user
from app.database.session import get_db
from app.models.audit import OpsAuditLog, OpsManifestSnapshot
from app.models.content import OpsContentBlock, OpsContentBlockVersion
from app.models.permission import OpsSectionPermission
from app.models.section import OpsSection
from app.models.service import OpsService
from app.models.user import OpsUser

router = APIRouter(prefix="/content", tags=["content"])


# ---------------------------------------------------------------------------
# 권한 헬퍼
# ---------------------------------------------------------------------------


async def _has_perm(
    db: AsyncSession, user: OpsUser, section_id: int, *, attr: str
) -> bool:
    if user.role == "ops_admin":
        return True
    perm = (
        await db.execute(
            select(OpsSectionPermission).where(
                OpsSectionPermission.user_id == user.id,
                OpsSectionPermission.section_id == section_id,
            )
        )
    ).scalar_one_or_none()
    return bool(perm and getattr(perm, attr))


async def _require_section_perm(
    db: AsyncSession, user: OpsUser, section_id: int, attr: str
):
    if not await _has_perm(db, user, section_id, attr=attr):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, f"권한 부족: {attr} (또는 ops_admin)"
        )


def _spec_to_dto(spec: ContentBlockSpec) -> ContentBlockSpecDTO:
    return ContentBlockSpecDTO(
        key=spec.key,
        format=spec.format,
        max_length=spec.max_length,
        locales=spec.locales,
        description=spec.description,
    )


async def _block_dto(
    db: AsyncSession,
    block: OpsContentBlock,
    *,
    section: OpsSection | None = None,
    service: OpsService | None = None,
    spec: ContentBlockSpec | None = None,
) -> ContentBlockDTO:
    if section is None:
        section = (
            await db.execute(select(OpsSection).where(OpsSection.id == block.section_id))
        ).scalar_one()
    if service is None:
        service = (
            await db.execute(select(OpsService).where(OpsService.id == section.service_id))
        ).scalar_one()
    if spec is None:
        try:
            spec = await fetch_block_spec(db, section, block.key)
        except ContentValidationError:
            spec = None

    return ContentBlockDTO(
        id=block.id,
        section_id=block.section_id,
        section_code=section.code,
        service_code=service.code,
        key=block.key,
        locale=block.locale,
        format=block.format,
        draft_body=block.draft_body,
        draft_edited_by=block.draft_edited_by,
        draft_edited_at=block.draft_edited_at,
        published_body=block.published_body,
        published_version=block.published_version,
        published_by=block.published_by,
        published_at=block.published_at,
        status=block.status,
        reviewer_id=block.reviewer_id,
        review_note=block.review_note,
        spec=_spec_to_dto(spec) if spec else None,
    )


# ---------------------------------------------------------------------------
# 매니페스트 화이트리스트 + 기존 row 조인
# ---------------------------------------------------------------------------


@router.get(
    "/sections/{service_code}/{section_code}/blocks",
    response_model=list[ContentBlockListItemDTO],
)
async def list_section_blocks(
    service_code: str,
    section_code: str,
    locale: str = "ko",
    _user: OpsUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ContentBlockListItemDTO]:
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

    # 매니페스트의 화이트리스트
    snap = (
        await db.execute(
            select(OpsManifestSnapshot)
            .where(OpsManifestSnapshot.service_id == svc.id)
            .order_by(OpsManifestSnapshot.fetched_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if snap is None:
        return []

    sections = snap.manifest.get("sections", [])
    section_def = next((s for s in sections if s.get("code") == section_code), None)
    blocks_def = (section_def or {}).get("content_blocks") or []

    # DB 의 기존 row
    db_rows = (
        await db.execute(
            select(OpsContentBlock).where(
                OpsContentBlock.section_id == section.id, OpsContentBlock.locale == locale
            )
        )
    ).scalars().all()
    by_key = {r.key: r for r in db_rows}

    out: list[ContentBlockListItemDTO] = []
    for bdef in blocks_def:
        spec = ContentBlockSpec(
            key=bdef["key"],
            format=bdef.get("format", "markdown"),
            max_length=int(bdef.get("max_length", 5000)),
            locales=list(bdef.get("locales") or ["ko"]),
            description=bdef.get("description"),
        )
        existing = by_key.get(spec.key)
        block_dto = (
            await _block_dto(db, existing, section=section, service=svc, spec=spec)
            if existing
            else None
        )
        out.append(ContentBlockListItemDTO(spec=_spec_to_dto(spec), block=block_dto))
    return out


@router.get("/blocks/{block_id}", response_model=ContentBlockDTO)
async def get_block(
    block_id: int,
    _user: OpsUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContentBlockDTO:
    block = (
        await db.execute(select(OpsContentBlock).where(OpsContentBlock.id == block_id))
    ).scalar_one_or_none()
    if block is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"block {block_id} 미존재")
    return await _block_dto(db, block)


# ---------------------------------------------------------------------------
# Draft 편집
# ---------------------------------------------------------------------------


@router.put(
    "/sections/{service_code}/{section_code}/blocks/{key}/draft",
    response_model=ContentBlockDTO,
)
async def save_draft(
    service_code: str,
    section_code: str,
    key: str,
    body: DraftSaveRequest,
    user: OpsUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContentBlockDTO:
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
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"section '{section_code}' 미존재")

    await _require_section_perm(db, user, section.id, "can_edit_content")

    # 화이트리스트 + 길이 검증
    try:
        spec = await fetch_block_spec(db, section, key)
        assert_writable(spec, body=body.body, locale=body.locale)
    except ContentValidationError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    block = (
        await db.execute(
            select(OpsContentBlock).where(
                OpsContentBlock.section_id == section.id,
                OpsContentBlock.key == key,
                OpsContentBlock.locale == body.locale,
            )
        )
    ).scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if block is None:
        block = OpsContentBlock(
            section_id=section.id,
            key=key,
            locale=body.locale,
            format=spec.format,
            draft_body=body.body,
            draft_edited_by=user.id,
            draft_edited_at=now,
            status="draft",
        )
        db.add(block)
    else:
        block.draft_body = body.body
        block.draft_edited_by = user.id
        block.draft_edited_at = now
        # pending_review 였으면 다시 draft 로 (편집 = 검토 결과 무효화)
        if block.status == "pending_review":
            block.status = "draft"
            block.reviewer_id = None
            block.review_note = None
        elif block.status == "published":
            block.status = "draft"  # 변경분이 있으니 다시 draft

    db.add(
        OpsAuditLog(
            actor_id=user.id,
            action="content_draft_saved",
            target_type="ops_content_blocks",
            target_id=str(block.id) if block.id else None,
            payload={"section_id": section.id, "key": key, "locale": body.locale, "len": len(body.body)},
        )
    )
    await db.commit()
    await db.refresh(block)
    return await _block_dto(db, block, section=section, service=svc, spec=spec)


# ---------------------------------------------------------------------------
# 워크플로
# ---------------------------------------------------------------------------


async def _load_block_with_section(
    db: AsyncSession, block_id: int
) -> tuple[OpsContentBlock, OpsSection, OpsService]:
    block = (
        await db.execute(select(OpsContentBlock).where(OpsContentBlock.id == block_id))
    ).scalar_one_or_none()
    if block is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"block {block_id} 미존재")
    section = (
        await db.execute(select(OpsSection).where(OpsSection.id == block.section_id))
    ).scalar_one()
    service = (
        await db.execute(select(OpsService).where(OpsService.id == section.service_id))
    ).scalar_one()
    return block, section, service


@router.post("/blocks/{block_id}/request-review", response_model=ContentBlockDTO)
async def request_review(
    block_id: int,
    body: ReviewRequest,
    user: OpsUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContentBlockDTO:
    block, section, svc = await _load_block_with_section(db, block_id)
    await _require_section_perm(db, user, section.id, "can_edit_content")

    if block.draft_body is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "draft_body 가 비어있음")
    if block.status not in ("draft", "published"):
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"현재 status 에서 검토 요청 불가: {block.status}"
        )

    block.status = "pending_review"
    block.review_note = None
    if body.reviewer_email:
        reviewer = (
            await db.execute(
                select(OpsUser).where(OpsUser.email == body.reviewer_email.lower())
            )
        ).scalar_one_or_none()
        block.reviewer_id = reviewer.id if reviewer else None
    db.add(
        OpsAuditLog(
            actor_id=user.id,
            action="content_review_requested",
            target_type="ops_content_blocks",
            target_id=str(block.id),
            payload={"reviewer_email": body.reviewer_email},
        )
    )
    await db.commit()
    await db.refresh(block)
    return await _block_dto(db, block, section=section, service=svc)


@router.post("/blocks/{block_id}/approve", response_model=ContentBlockDTO)
async def approve(
    block_id: int,
    body: ReviewDecisionRequest,
    user: OpsUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContentBlockDTO:
    block, section, svc = await _load_block_with_section(db, block_id)
    # 승인은 can_publish 보유자 또는 ops_admin
    await _require_section_perm(db, user, section.id, "can_publish")

    if block.status != "pending_review":
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"pending_review 상태가 아님: {block.status}"
        )

    block.reviewer_id = user.id
    block.review_note = body.note
    # 승인 = 즉시 게시
    await publish_block(db, block, publisher=user)
    db.add(
        OpsAuditLog(
            actor_id=user.id,
            action="content_approved_and_published",
            target_type="ops_content_blocks",
            target_id=str(block.id),
            payload={"version": block.published_version, "note": body.note},
        )
    )
    await db.commit()
    await db.refresh(block)
    return await _block_dto(db, block, section=section, service=svc)


@router.post("/blocks/{block_id}/reject", response_model=ContentBlockDTO)
async def reject(
    block_id: int,
    body: ReviewDecisionRequest,
    user: OpsUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContentBlockDTO:
    block, section, svc = await _load_block_with_section(db, block_id)
    await _require_section_perm(db, user, section.id, "can_publish")

    if block.status != "pending_review":
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"pending_review 상태가 아님: {block.status}"
        )

    block.reviewer_id = user.id
    block.review_note = body.note
    block.status = "draft"
    db.add(
        OpsAuditLog(
            actor_id=user.id,
            action="content_rejected",
            target_type="ops_content_blocks",
            target_id=str(block.id),
            payload={"note": body.note},
        )
    )
    await db.commit()
    await db.refresh(block)
    return await _block_dto(db, block, section=section, service=svc)


@router.post("/blocks/{block_id}/publish", response_model=ContentBlockDTO)
async def publish_directly(
    block_id: int,
    user: OpsUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContentBlockDTO:
    """검토 단계 생략 게시 (긴급용) — can_publish 보유자만."""
    block, section, svc = await _load_block_with_section(db, block_id)
    await _require_section_perm(db, user, section.id, "can_publish")

    if block.status not in ("draft", "pending_review", "published"):
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"게시 불가 status: {block.status}"
        )
    await publish_block(db, block, publisher=user)
    db.add(
        OpsAuditLog(
            actor_id=user.id,
            action="content_published_direct",
            target_type="ops_content_blocks",
            target_id=str(block.id),
            payload={"version": block.published_version},
        )
    )
    await db.commit()
    await db.refresh(block)
    return await _block_dto(db, block, section=section, service=svc)


@router.get("/blocks/{block_id}/versions", response_model=list[dict])
async def list_versions(
    block_id: int,
    _user: OpsUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    rows = (
        await db.execute(
            select(OpsContentBlockVersion)
            .where(OpsContentBlockVersion.block_id == block_id)
            .order_by(OpsContentBlockVersion.version.desc())
        )
    ).scalars().all()
    return [
        {
            "id": r.id,
            "version": r.version,
            "edited_by": r.edited_by,
            "edited_at": r.edited_at.isoformat(),
            "body": r.body,
        }
        for r in rows
    ]
