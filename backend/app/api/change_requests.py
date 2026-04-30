"""POST/GET/PATCH /api/change-requests — 변경요청 CRUD + GitHub Issue 자동 발급."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dto import (
    AttachmentDTO,
    ChangeRequestCreateRequest,
    ChangeRequestDTO,
    ChangeRequestPatchRequest,
)
from app.core.security import get_current_user
from app.database.session import get_db
from app.github import client as gh_client
from app.github.issue_builder import build_issue_body, build_issue_title, build_labels
from app.models.audit import OpsAuditLog
from app.models.change_request import OpsChangeRequest, OpsChangeRequestEvent
from app.models.section import OpsSection, OpsSectionAsset
from app.models.service import OpsService
from app.models.user import OpsUser

log = logging.getLogger("opsconsole.api.change_requests")

router = APIRouter(prefix="/change-requests", tags=["change-requests"])


# ---------------------------------------------------------------------------
# DTO 변환 (배치 시에는 join 으로 해결, 단건은 보조 query)
# ---------------------------------------------------------------------------


async def _enrich_dto(
    db: AsyncSession, cr: OpsChangeRequest
) -> ChangeRequestDTO:
    requester = (
        await db.execute(select(OpsUser).where(OpsUser.id == cr.requester_id))
    ).scalar_one()
    section: OpsSection | None = None
    service: OpsService | None = None
    if cr.section_id is not None:
        section = (
            await db.execute(select(OpsSection).where(OpsSection.id == cr.section_id))
        ).scalar_one_or_none()
        if section:
            service = (
                await db.execute(
                    select(OpsService).where(OpsService.id == section.service_id)
                )
            ).scalar_one_or_none()

    return ChangeRequestDTO(
        id=cr.id,
        section_id=cr.section_id,
        section_code=section.code if section else None,
        service_code=service.code if service else None,
        requester_id=cr.requester_id,
        requester_email=requester.email,
        title=cr.title,
        description_md=cr.description_md,
        status=cr.status,
        priority=cr.priority,
        github_issue_url=cr.github_issue_url,
        github_issue_number=cr.github_issue_number,
        github_pr_url=cr.github_pr_url,
        github_pr_number=cr.github_pr_number,
        attachments=[AttachmentDTO.model_validate(a) for a in cr.attachments]
        if cr.attachments
        else None,
        created_at=cr.created_at,
        updated_at=cr.updated_at,
        closed_at=cr.closed_at,
    )


# ---------------------------------------------------------------------------
# POST /api/change-requests
# ---------------------------------------------------------------------------


@router.post("", response_model=ChangeRequestDTO, status_code=status.HTTP_201_CREATED)
async def create_change_request(
    body: ChangeRequestCreateRequest,
    user: OpsUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChangeRequestDTO:
    section: OpsSection | None = None
    service: OpsService | None = None
    if body.section_id is not None:
        section = (
            await db.execute(select(OpsSection).where(OpsSection.id == body.section_id))
        ).scalar_one_or_none()
        if section is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"section {body.section_id} 미존재")
        service = (
            await db.execute(select(OpsService).where(OpsService.id == section.service_id))
        ).scalar_one()

    cr = OpsChangeRequest(
        section_id=body.section_id,
        requester_id=user.id,
        title=body.title.strip(),
        description_md=body.description_md,
        priority=body.priority,
        status="submitted",
        attachments=[a.model_dump() for a in body.attachments] if body.attachments else None,
    )
    db.add(cr)
    await db.flush()  # cr.id 확보

    db.add(
        OpsChangeRequestEvent(
            request_id=cr.id, event_type="created", payload={"actor_id": user.id}
        )
    )

    # GitHub Issue 자동 발급 (조건: skip 아님 + service.repo_url 보유 + GITHUB_PAT 보유)
    if not body.skip_github and service and service.repo_url:
        assets: list[OpsSectionAsset] = []
        if section:
            assets = list(
                (
                    await db.execute(
                        select(OpsSectionAsset).where(OpsSectionAsset.section_id == section.id)
                    )
                ).scalars().all()
            )
        title = build_issue_title(cr, section)
        gh_body = build_issue_body(
            cr,
            requester=user,
            service=service,
            section=section,
            assets=assets,
        )
        labels = build_labels(section, cr.priority)
        try:
            issue = await gh_client.create_issue(
                service.repo_url, title=title, body=gh_body, labels=labels
            )
        except gh_client.GitHubError as e:
            log.warning("[change_request] GitHub issue 발급 실패: %s", e)
            db.add(
                OpsChangeRequestEvent(
                    request_id=cr.id,
                    event_type="issue_create_failed",
                    payload={"error": str(e)[:500]},
                )
            )
        else:
            cr.github_issue_url = issue.get("html_url")
            cr.github_issue_number = issue.get("number")
            db.add(
                OpsChangeRequestEvent(
                    request_id=cr.id,
                    event_type="issue_opened",
                    payload={
                        "issue_number": issue.get("number"),
                        "html_url": issue.get("html_url"),
                    },
                )
            )

    db.add(
        OpsAuditLog(
            actor_id=user.id,
            action="change_request_created",
            target_type="ops_change_requests",
            target_id=str(cr.id),
            payload={
                "section_id": body.section_id,
                "title": body.title,
                "priority": body.priority,
                "issue_number": cr.github_issue_number,
            },
        )
    )

    await db.commit()
    await db.refresh(cr)
    return await _enrich_dto(db, cr)


# ---------------------------------------------------------------------------
# GET / GET {id} / PATCH / DELETE
# ---------------------------------------------------------------------------


@router.get("", response_model=list[ChangeRequestDTO])
async def list_change_requests(
    section_id: int | None = Query(default=None),
    requester_email: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    mine: bool = Query(default=False),
    user: OpsUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ChangeRequestDTO]:
    stmt = select(OpsChangeRequest).order_by(OpsChangeRequest.id.desc())
    if section_id is not None:
        stmt = stmt.where(OpsChangeRequest.section_id == section_id)
    if mine:
        stmt = stmt.where(OpsChangeRequest.requester_id == user.id)
    elif requester_email:
        target = (
            await db.execute(
                select(OpsUser).where(OpsUser.email == requester_email.lower())
            )
        ).scalar_one_or_none()
        if target is None:
            return []
        stmt = stmt.where(OpsChangeRequest.requester_id == target.id)
    if status_filter:
        stmt = stmt.where(OpsChangeRequest.status == status_filter)

    rows = (await db.execute(stmt)).scalars().all()
    return [await _enrich_dto(db, r) for r in rows]


@router.get("/{cr_id}", response_model=ChangeRequestDTO)
async def get_change_request(
    cr_id: int,
    _user: OpsUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChangeRequestDTO:
    cr = (
        await db.execute(select(OpsChangeRequest).where(OpsChangeRequest.id == cr_id))
    ).scalar_one_or_none()
    if cr is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"change_request {cr_id} 미존재")
    return await _enrich_dto(db, cr)


@router.patch("/{cr_id}", response_model=ChangeRequestDTO)
async def patch_change_request(
    cr_id: int,
    body: ChangeRequestPatchRequest,
    user: OpsUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChangeRequestDTO:
    cr = (
        await db.execute(select(OpsChangeRequest).where(OpsChangeRequest.id == cr_id))
    ).scalar_one_or_none()
    if cr is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"change_request {cr_id} 미존재")

    # 작성자 본인만 title/desc/priority 수정 가능. status 는 ops_admin 만.
    if any(v is not None for v in (body.title, body.description_md, body.priority)):
        if cr.requester_id != user.id and user.role != "ops_admin":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "본인 또는 ops_admin 만 수정 가능")
        if body.title is not None:
            cr.title = body.title.strip()
        if body.description_md is not None:
            cr.description_md = body.description_md
        if body.priority is not None:
            cr.priority = body.priority

    if body.status is not None:
        if user.role != "ops_admin":
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "status 변경은 ops_admin 만 가능"
            )
        cr.status = body.status
        if body.status in ("merged", "closed", "rejected") and cr.closed_at is None:
            cr.closed_at = datetime.now(timezone.utc)

    db.add(
        OpsAuditLog(
            actor_id=user.id,
            action="change_request_patched",
            target_type="ops_change_requests",
            target_id=str(cr.id),
            payload=body.model_dump(exclude_none=True),
        )
    )
    await db.commit()
    await db.refresh(cr)
    return await _enrich_dto(db, cr)
