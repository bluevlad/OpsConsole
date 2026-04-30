"""JWT 발급·검증 + Google ID 토큰 검증.

ops_users.role: ops_admin / ops_member / ops_viewer
- ADR-001: 본 서비스(예: AllergyInsight)의 super_admin 과 별개 모델.
- AllergyInsight Google OAuth Client ID 를 재사용해도 무방 (audience만 일치하면 됨).
  단, JWT 시크릿/유저 테이블/role 모델은 OpsConsole 자체.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.database.session import get_db
from app.models.user import OpsUser

bearer_scheme = HTTPBearer(auto_error=False)


# -- JWT --------------------------------------------------------------------


def create_access_token(user: OpsUser) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt_access_token_expire_minutes
    )
    payload: dict[str, Any] = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid JWT: {e}") from e


# -- Google ID token --------------------------------------------------------


def verify_google_id_token(credential: str) -> dict[str, Any]:
    """Google ID 토큰 → 사용자 정보 dict (sub/email/name/picture).

    AllergyInsight 와 동일한 패턴 (google.oauth2.id_token.verify_oauth2_token).
    audience 는 OpsConsole 의 GOOGLE_OAUTH_CLIENT_ID 와 일치해야 한다.
    """
    if not settings.google_oauth_client_id:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "GOOGLE_OAUTH_CLIENT_ID 미설정",
        )
    try:
        idinfo = id_token.verify_oauth2_token(
            credential,
            google_requests.Request(),
            settings.google_oauth_client_id,
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid Google credential: {e}") from e

    if idinfo.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid Google issuer")
    if not idinfo.get("email_verified", False):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email not verified")
    return idinfo


# -- FastAPI dependency: 현재 사용자 ----------------------------------------


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> OpsUser:
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bearer token required")

    payload = decode_token(creds.credentials)
    user_id = int(payload.get("sub", 0))
    if not user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token subject")

    user = (
        await db.execute(select(OpsUser).where(OpsUser.id == user_id))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return user


# P5 — 역할 위계: admin > reviewer > member > viewer
ROLE_RANK = {
    "ops_viewer": 0,
    "ops_member": 1,
    "ops_reviewer": 2,
    "ops_admin": 3,
}
VALID_ROLES = tuple(ROLE_RANK.keys())


def role_at_least(user: OpsUser, minimum: str) -> bool:
    return ROLE_RANK.get(user.role, -1) >= ROLE_RANK.get(minimum, 99)


def require_role(*allowed: str):
    """역할 게이트.

    - `require_role("ops_admin")` 처럼 정확한 매칭 또는
    - `require_role(min="ops_reviewer")` 형태(`min:` prefix)로 위계 사용.

    P5 권한 매트릭스:
    - ops_viewer  : 카탈로그 읽기
    - ops_member  : 위 + 변경요청 발급, 자기 섹션 콘텐츠 편집(권한 부여 시)
    - ops_reviewer: 위 + 콘텐츠 검토·게시(권한 부여 시), 헬스 모니터링
    - ops_admin   : 위 + 매니페스트 sync, 담당자 지정, 감사 로그 조회, 모든 admin
    """
    minimum: str | None = None
    exact: tuple[str, ...] = tuple()
    for a in allowed:
        if a.startswith("min:"):
            minimum = a[4:]
        else:
            exact = exact + (a,)

    async def _checker(user: OpsUser = Depends(get_current_user)) -> OpsUser:
        ok = False
        if exact and user.role in exact:
            ok = True
        if not ok and minimum and role_at_least(user, minimum):
            ok = True
        if not ok:
            allowed_label = list(exact) + ([f">= {minimum}"] if minimum else [])
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"role '{user.role}' 부족 — required: {allowed_label}",
            )
        return user

    return _checker
