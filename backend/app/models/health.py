"""ops_health_snapshots + ops_alert_state — 5분 주기 헬스 시계열 + 알림 디듀프."""
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class OpsHealthSnapshot(Base):
    __tablename__ = "ops_health_snapshots"
    __table_args__ = (
        Index("ix_health_section_time", "section_id", "checked_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    section_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ops_sections.id", ondelete="CASCADE"), nullable=False
    )
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ok: Mapped[bool] = mapped_column(Boolean, default=False)
    error_text: Mapped[str | None] = mapped_column(String, nullable=True)


class OpsAlertState(Base):
    """섹션별 알림 상태 — Slack 알림 스팸 방지.

    - consecutive_failures: 연속 실패 횟수 (3 도달 시 알림)
    - last_alerted_at: 가장 최근 알림 발송 시각 (cooldown 1h)
    - resolved_notified: 회복 알림이 이미 보내졌는지 (실패→회복 1회 알림 후 True)
    """

    __tablename__ = "ops_alert_state"

    section_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("ops_sections.id", ondelete="CASCADE"),
        primary_key=True,
    )
    last_alerted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    resolved_notified: Mapped[bool] = mapped_column(Boolean, default=True)
