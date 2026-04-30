"""POST/GET/DELETE /api/assignments — 섹션 × 사용자 권한 (ops_admin 만)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dto import AssignmentDTO, AssignmentRequest
from app.core.security import require_role
from app.database.session import get_db
from app.models.audit import OpsAuditLog
from app.models.permission import OpsSectionPermission
from app.models.section import OpsSection
from app.models.user import OpsUser

router = APIRouter(prefix="/assignments", tags=["assignments"])


def _to_dto(perm: OpsSectionPermission, user: OpsUser | None) -> AssignmentDTO:
    return AssignmentDTO(
        id=perm.id,
        section_id=perm.section_id,
        user_id=perm.user_id,
        user_email=user.email if user else None,
        user_name=user.name if user else None,
        can_edit_content=perm.can_edit_content,
        can_open_pr=perm.can_open_pr,
        can_publish=perm.can_publish,
        granted_at=perm.granted_at,
    )


@router.get("", response_model=list[AssignmentDTO])
async def list_assignments(
    section_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    _admin: OpsUser = Depends(require_role("ops_admin")),
) -> list[AssignmentDTO]:
    stmt = select(OpsSectionPermission, OpsUser).join(
        OpsUser, OpsUser.id == OpsSectionPermission.user_id
    )
    if section_id is not None:
        stmt = stmt.where(OpsSectionPermission.section_id == section_id)
    stmt = stmt.order_by(OpsSectionPermission.section_id, OpsUser.email)
    rows = (await db.execute(stmt)).all()
    return [_to_dto(perm, user) for perm, user in rows]


@router.post("", response_model=AssignmentDTO, status_code=status.HTTP_201_CREATED)
async def create_or_update_assignment(
    body: AssignmentRequest,
    db: AsyncSession = Depends(get_db),
    admin: OpsUser = Depends(require_role("ops_admin")),
) -> AssignmentDTO:
    section = (
        await db.execute(select(OpsSection).where(OpsSection.id == body.section_id))
    ).scalar_one_or_none()
    if section is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"section {body.section_id} 미존재")

    target_user = (
        await db.execute(select(OpsUser).where(OpsUser.email == body.user_email.lower()))
    ).scalar_one_or_none()
    if target_user is None:
        # 운영자가 아직 OpsConsole에 로그인한 적이 없으면 placeholder 생성
        target_user = OpsUser(email=body.user_email.lower(), name=None, role="ops_member")
        db.add(target_user)
        await db.flush()

    existing = (
        await db.execute(
            select(OpsSectionPermission).where(
                OpsSectionPermission.section_id == body.section_id,
                OpsSectionPermission.user_id == target_user.id,
            )
        )
    ).scalar_one_or_none()

    if existing is None:
        perm = OpsSectionPermission(
            section_id=body.section_id,
            user_id=target_user.id,
            can_edit_content=body.can_edit_content,
            can_open_pr=body.can_open_pr,
            can_publish=body.can_publish,
        )
        db.add(perm)
        action = "permission_granted"
    else:
        existing.can_edit_content = body.can_edit_content
        existing.can_open_pr = body.can_open_pr
        existing.can_publish = body.can_publish
        perm = existing
        action = "permission_updated"

    db.add(
        OpsAuditLog(
            actor_id=admin.id,
            action=action,
            target_type="ops_section_permissions",
            target_id=str(perm.id) if perm.id else None,
            payload={
                "section_id": body.section_id,
                "user_email": target_user.email,
                "can_edit_content": body.can_edit_content,
                "can_open_pr": body.can_open_pr,
                "can_publish": body.can_publish,
            },
        )
    )
    await db.commit()
    await db.refresh(perm)
    return _to_dto(perm, target_user)


@router.delete("/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def revoke_assignment(
    assignment_id: int,
    db: AsyncSession = Depends(get_db),
    admin: OpsUser = Depends(require_role("ops_admin")),
) -> None:
    perm = (
        await db.execute(
            select(OpsSectionPermission).where(OpsSectionPermission.id == assignment_id)
        )
    ).scalar_one_or_none()
    if perm is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"assignment {assignment_id} 미존재")

    payload = {
        "section_id": perm.section_id,
        "user_id": perm.user_id,
    }
    await db.delete(perm)
    db.add(
        OpsAuditLog(
            actor_id=admin.id,
            action="permission_revoked",
            target_type="ops_section_permissions",
            target_id=str(assignment_id),
            payload=payload,
        )
    )
    await db.commit()
