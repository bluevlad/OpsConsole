"""디바이스 코드 OAuth 흐름 (RFC 8628 단순화).

라우트:
  POST /api/auth/device/init                — 디바이스가 device_code/user_code 발급
  POST /api/auth/device/poll                — 디바이스가 access_token 폴링
  GET  /api/auth/device/lookup?user_code=X  — 웹이 user_code 메타 조회 (확인 화면용)
  POST /api/auth/device/approve             — 웹(로그인된 사용자)이 user_code 승인

보안:
- device_code: 32자 url-safe random (디바이스만 보유, 절대 노출 금지)
- user_code: 6자 8자 영숫자 (사용자 입력용, 하이픈 표기 'ABCD-EFGH')
- expires_at: 발급 후 10분
- 승인 후 디바이스가 한 번 폴링하여 redeem (redeemed_at 기록), 이후 동일 device_code 재사용 불가
"""
from __future__ import annotations

import secrets
import string
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, get_current_user
from app.database.session import get_db
from app.models.audit import OpsAuditLog
from app.models.device_code import OpsDeviceCode
from app.models.user import OpsUser

router = APIRouter(prefix="/auth/device", tags=["device-auth"])

DEVICE_CODE_TTL = timedelta(minutes=10)
POLL_INTERVAL_S = 5
USER_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # 헷갈리는 0/O/1/I 제외


def _gen_device_code() -> str:
    return secrets.token_urlsafe(32)


def _gen_user_code() -> str:
    """8자 → 'ABCD-EFGH' 형식. 충돌 가능성 매우 낮음 (32^8 ~= 1.1e12)."""
    raw = "".join(secrets.choice(USER_CODE_ALPHABET) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


# ---------------------------------------------------------------------------
# Request / Response 스키마
# ---------------------------------------------------------------------------


class DeviceInitRequest(BaseModel):
    device_label: str | None = Field(default=None, max_length=100)
    user_agent: str | None = Field(default=None, max_length=200)


class DeviceInitResponse(BaseModel):
    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int


class DevicePollRequest(BaseModel):
    device_code: str


class DevicePollPendingResponse(BaseModel):
    status: str  # 'pending' / 'expired'


class DevicePollSuccessResponse(BaseModel):
    status: str = "approved"
    access_token: str
    token_type: str = "bearer"
    user: dict


class DeviceLookupResponse(BaseModel):
    user_code: str
    device_label: str | None
    user_agent: str | None
    expires_at: datetime
    approved: bool


class DeviceApproveRequest(BaseModel):
    user_code: str


# ---------------------------------------------------------------------------
# 1) init — 디바이스 토큰 발급 요청
# ---------------------------------------------------------------------------


@router.post("/init", response_model=DeviceInitResponse)
async def device_init(
    body: DeviceInitRequest, db: AsyncSession = Depends(get_db)
) -> DeviceInitResponse:
    # user_code 충돌 시 재시도 (최대 5번)
    for _ in range(5):
        user_code = _gen_user_code()
        clash = (
            await db.execute(
                select(OpsDeviceCode.device_code).where(OpsDeviceCode.user_code == user_code)
            )
        ).first()
        if not clash:
            break
    else:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "user_code 충돌")

    expires_at = datetime.now(timezone.utc) + DEVICE_CODE_TTL
    row = OpsDeviceCode(
        device_code=_gen_device_code(),
        user_code=user_code,
        expires_at=expires_at,
        device_label=body.device_label,
        user_agent=body.user_agent,
    )
    db.add(row)
    await db.commit()

    return DeviceInitResponse(
        device_code=row.device_code,
        user_code=user_code,
        verification_uri="https://opsconsole.unmong.com/device",
        expires_in=int(DEVICE_CODE_TTL.total_seconds()),
        interval=POLL_INTERVAL_S,
    )


# ---------------------------------------------------------------------------
# 2) poll — 디바이스가 토큰 폴링
# ---------------------------------------------------------------------------


@router.post("/poll", response_model=DevicePollSuccessResponse | DevicePollPendingResponse)
async def device_poll(body: DevicePollRequest, db: AsyncSession = Depends(get_db)):
    row = (
        await db.execute(
            select(OpsDeviceCode).where(OpsDeviceCode.device_code == body.device_code)
        )
    ).scalar_one_or_none()

    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "device_code 미존재")

    now = datetime.now(timezone.utc)
    if row.expires_at < now:
        return DevicePollPendingResponse(status="expired")
    if not row.approved or row.user_id is None:
        return DevicePollPendingResponse(status="pending")
    if row.redeemed_at is not None:
        # 이미 redeem 됨 — 한 번만 사용 가능
        raise HTTPException(status.HTTP_410_GONE, "이미 사용된 device_code")

    user = (
        await db.execute(select(OpsUser).where(OpsUser.id == row.user_id))
    ).scalar_one()
    token = create_access_token(user)

    row.redeemed_at = now
    db.add(
        OpsAuditLog(
            actor_id=user.id,
            action="device_redeemed",
            target_type="ops_device_codes",
            target_id=row.device_code[:12],  # 일부만 (감사 + 식별용)
            payload={"device_label": row.device_label},
        )
    )
    await db.commit()

    return DevicePollSuccessResponse(
        access_token=token,
        user={"id": user.id, "email": user.email, "name": user.name, "role": user.role},
    )


# ---------------------------------------------------------------------------
# 3) lookup — 웹 승인 화면이 user_code 메타 조회
# ---------------------------------------------------------------------------


@router.get("/lookup", response_model=DeviceLookupResponse)
async def device_lookup(
    user_code: str,
    _user: OpsUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DeviceLookupResponse:
    row = (
        await db.execute(
            select(OpsDeviceCode).where(OpsDeviceCode.user_code == user_code.upper())
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"user_code '{user_code}' 미존재")
    if row.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_410_GONE, "user_code 만료")
    return DeviceLookupResponse(
        user_code=row.user_code,
        device_label=row.device_label,
        user_agent=row.user_agent,
        expires_at=row.expires_at,
        approved=row.approved,
    )


# ---------------------------------------------------------------------------
# 4) approve — 웹의 로그인된 사용자가 user_code 승인
# ---------------------------------------------------------------------------


@router.post("/approve")
async def device_approve(
    body: DeviceApproveRequest,
    user: OpsUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = (
        await db.execute(
            select(OpsDeviceCode).where(OpsDeviceCode.user_code == body.user_code.upper())
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"user_code 미존재")
    now = datetime.now(timezone.utc)
    if row.expires_at < now:
        raise HTTPException(status.HTTP_410_GONE, "user_code 만료")
    if row.approved and row.user_id is not None:
        return {"status": "already_approved"}

    row.approved = True
    row.user_id = user.id

    db.add(
        OpsAuditLog(
            actor_id=user.id,
            action="device_approved",
            target_type="ops_device_codes",
            target_id=row.device_code[:12],
            payload={
                "device_label": row.device_label,
                "user_agent": row.user_agent,
            },
        )
    )
    await db.commit()
    return {"status": "approved"}
