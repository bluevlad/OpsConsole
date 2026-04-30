"""ops_change_requests + ops_change_request_events — 변경요청 폼 + GitHub 동기화."""
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class OpsChangeRequest(Base):
    __tablename__ = "ops_change_requests"
    __table_args__ = (
        Index("ix_cr_section", "section_id"),
        Index("ix_cr_requester", "requester_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    section_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("ops_sections.id", ondelete="SET NULL"), nullable=True
    )
    requester_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ops_users.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String, nullable=False)
    description_md: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="submitted")
    # submitted / in_pr / merged / closed / rejected
    github_issue_url: Mapped[str | None] = mapped_column(String, nullable=True)
    github_issue_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    github_pr_url: Mapped[str | None] = mapped_column(String, nullable=True)
    github_pr_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attachments: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    priority: Mapped[str] = mapped_column(String, default="normal")
    # low / normal / high / urgent
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OpsChangeRequestEvent(Base):
    """변경요청 1건의 lifecycle 이벤트 (감사 + idempotency 키).

    github_event_id (X-GitHub-Delivery 헤더) 로 webhook 재시도 디듀프.
    """

    __tablename__ = "ops_change_request_events"
    __table_args__ = (
        Index("ix_cr_event_request", "request_id"),
        Index("ix_cr_event_github_id", "github_event_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    request_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("ops_change_requests.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str | None] = mapped_column(String, nullable=True)
    # created / issue_opened / pr_opened / pr_merged / issue_closed / closed / rejected
    github_event_id: Mapped[str | None] = mapped_column(String, nullable=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
