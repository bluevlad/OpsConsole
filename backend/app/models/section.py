"""ops_sections + ops_section_assets — 서비스별 섹션 카탈로그와 자산 매핑."""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class OpsSection(Base):
    __tablename__ = "ops_sections"
    __table_args__ = (UniqueConstraint("service_id", "code", name="uq_section_service_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    service_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ops_services.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    level: Mapped[str] = mapped_column(String, nullable=False)  # public/member/admin
    route: Mapped[str | None] = mapped_column(String, nullable=True)
    owner_email: Mapped[str | None] = mapped_column(String, nullable=True)
    backup_email: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="live")  # live/beta/deprecated
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class OpsSectionAsset(Base):
    __tablename__ = "ops_section_assets"
    __table_args__ = (Index("ix_assets_section", "section_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    section_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ops_sections.id", ondelete="CASCADE"), nullable=False
    )
    asset_type: Mapped[str] = mapped_column(String, nullable=False)
    # frontend / backend_router / service / model / table / endpoint
    path: Mapped[str] = mapped_column(String, nullable=False)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)
