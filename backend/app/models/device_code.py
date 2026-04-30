"""ops_device_codes — Tauri 트레이 앱 디바이스 코드 흐름.

흐름:
1. 트레이 앱 → POST /auth/device/init → device_code, user_code 받음
2. 트레이 앱 → 사용자에게 user_code 표시 + 브라우저 오픈 (/device)
3. 사용자 (이미 로그인된 상태) 가 user_code 입력 + 승인
4. 트레이 앱 → POST /auth/device/poll {device_code} → access_token + refresh_token
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class OpsDeviceCode(Base):
    __tablename__ = "ops_device_codes"
    __table_args__ = (
        Index("ix_device_user_code", "user_code"),
    )

    device_code: Mapped[str] = mapped_column(String, primary_key=True)
    user_code: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("ops_users.id"), nullable=True
    )
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    redeemed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # 디바이스 식별 메타 (선택, 감사 + 폐기용)
    device_label: Mapped[str | None] = mapped_column(String, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String, nullable=True)
