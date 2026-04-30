"""POST /api/auth/google/verify, GET /api/auth/me.

흐름:
1. 프런트가 Google Identity Services로 credential(JWT) 획득
2. POST /api/auth/google/verify { credential } → 백엔드에서 ID token 검증
3. ops_users upsert (이메일 기준), 첫 가입자는 ops_admin (P0 부트스트랩 정책 — P5에서 화이트리스트로 강화)
4. OpsConsole 자체 JWT 발급 후 반환
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    get_current_user,
    verify_google_id_token,
)
from app.database.session import get_db
from app.models.audit import OpsAuditLog
from app.models.user import OpsUser

router = APIRouter(prefix="/auth", tags=["auth"])


class GoogleVerifyRequest(BaseModel):
    credential: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class MeResponse(BaseModel):
    id: int
    email: str
    name: str | None
    role: str
    last_login_at: datetime | None


@router.post("/google/verify", response_model=TokenResponse)
async def google_verify(
    body: GoogleVerifyRequest, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    idinfo = verify_google_id_token(body.credential)

    email: str = (idinfo.get("email") or "").lower()
    if not email:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Google credential lacks email")

    name: str | None = idinfo.get("name") or email.split("@")[0]
    sub: str = idinfo.get("sub", "")

    # 이메일 기준 upsert
    user = (
        await db.execute(select(OpsUser).where(OpsUser.email == email))
    ).scalar_one_or_none()

    if user is None:
        # 첫 운영자 부트스트랩: 등록된 사용자가 없으면 ops_admin, 그 외엔 ops_member
        # P5 에서 운영자 화이트리스트 / 도메인 제한 / 초대 토큰 등으로 강화.
        total = (await db.execute(select(func.count(OpsUser.id)))).scalar_one()
        role = "ops_admin" if total == 0 else "ops_member"
        user = OpsUser(email=email, name=name, role=role, github_login=None)
        db.add(user)
        await db.flush()
        action = "user_created"
    else:
        if name and user.name != name:
            user.name = name
        action = "user_login"

    user.last_login_at = datetime.now(timezone.utc)

    db.add(
        OpsAuditLog(
            actor_id=user.id,
            action=action,
            target_type="ops_users",
            target_id=str(user.id),
            payload={"email": email, "google_sub": sub, "role": user.role},
        )
    )
    await db.commit()
    await db.refresh(user)

    token = create_access_token(user)
    return TokenResponse(
        access_token=token,
        user={
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role,
        },
    )


@router.get("/me", response_model=MeResponse)
async def me(user: OpsUser = Depends(get_current_user)) -> MeResponse:
    return MeResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        last_login_at=user.last_login_at,
    )
