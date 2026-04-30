"""ops_section_permissions — 섹션 × 사용자 권한.

P1 단계: 권한 부여/해제만. P3 (콘텐츠 에디터)에서 can_edit_content/can_publish 본격 사용.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class OpsSectionPermission(Base):
    __tablename__ = "ops_section_permissions"
    __table_args__ = (UniqueConstraint("section_id", "user_id", name="uq_perm_section_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    section_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ops_sections.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ops_users.id", ondelete="CASCADE"), nullable=False
    )
    can_edit_content: Mapped[bool] = mapped_column(Boolean, default=False)
    can_open_pr: Mapped[bool] = mapped_column(Boolean, default=True)
    can_publish: Mapped[bool] = mapped_column(Boolean, default=False)
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
