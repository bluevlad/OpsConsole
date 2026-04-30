"""ops_content_blocks + ops_content_block_versions — 콘텐츠 블록 + 버전 이력.

워크플로:
  draft → pending_review → published
                       ↘ draft (반려)
                  published → archived (deprecate)
"""
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class OpsContentBlock(Base):
    __tablename__ = "ops_content_blocks"
    __table_args__ = (
        UniqueConstraint("section_id", "key", "locale", name="uq_block_section_key_locale"),
        Index("ix_block_status", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    section_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ops_sections.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(String, nullable=False)
    # ex: 'ai_consult.intro_banner'
    locale: Mapped[str] = mapped_column(String, default="ko")
    format: Mapped[str] = mapped_column(String, default="markdown")
    # markdown / text / html(sanitized)

    draft_body: Mapped[str | None] = mapped_column(String, nullable=True)
    draft_edited_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("ops_users.id"), nullable=True
    )
    draft_edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    published_body: Mapped[str | None] = mapped_column(String, nullable=True)
    published_version: Mapped[int] = mapped_column(Integer, default=0)
    published_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("ops_users.id"), nullable=True
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    status: Mapped[str] = mapped_column(String, default="draft")
    # draft / pending_review / published / archived
    reviewer_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("ops_users.id"), nullable=True
    )
    review_note: Mapped[str | None] = mapped_column(String, nullable=True)


class OpsContentBlockVersion(Base):
    """게시 시 스냅샷 — published_version 증가하며 행 추가."""

    __tablename__ = "ops_content_block_versions"
    __table_args__ = (
        UniqueConstraint("block_id", "version", name="uq_block_version"),
        Index("ix_block_version_block", "block_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    block_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("ops_content_blocks.id", ondelete="CASCADE"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    body: Mapped[str | None] = mapped_column(String, nullable=True)
    edited_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("ops_users.id"), nullable=True
    )
    edited_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
