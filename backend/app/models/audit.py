"""ops_audit_log + ops_manifest_snapshots — 감사 로그와 매니페스트 시계열."""
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class OpsAuditLog(Base):
    __tablename__ = "ops_audit_log"
    __table_args__ = (Index("ix_audit_at", "at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("ops_users.id"), nullable=True
    )
    action: Mapped[str] = mapped_column(String, nullable=False)
    # 'sync_manifest' / 'update_section' / 'publish_content' / ...
    target_type: Mapped[str | None] = mapped_column(String, nullable=True)
    target_id: Mapped[str | None] = mapped_column(String, nullable=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OpsManifestSnapshot(Base):
    __tablename__ = "ops_manifest_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    service_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ops_services.id"), nullable=False
    )
    ref: Mapped[str] = mapped_column(String, nullable=False)  # git ref / SHA
    manifest: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
