"""API 응답 DTO — ORM 직렬화 / 매니페스트 sync 결과 / 헬스 / 권한."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class _OrmDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# -- Catalog ----------------------------------------------------------------


class ServiceDTO(_OrmDTO):
    id: int
    code: str
    display_name: str
    gateway_url: str | None
    repo_url: str | None
    status: str
    last_synced_at: datetime | None
    section_count: int = 0  # 카탈로그 목록에서 미리 표시


class SectionAssetDTO(_OrmDTO):
    asset_type: str
    path: str
    notes: str | None = None


class SectionDTO(_OrmDTO):
    id: int
    code: str
    name: str
    level: str
    route: str | None
    owner_email: str | None
    backup_email: str | None
    status: str
    assets: list[SectionAssetDTO] = Field(default_factory=list)
    health: "SectionHealthSummaryDTO | None" = None


# -- Sync -------------------------------------------------------------------


class SyncRequest(BaseModel):
    """POST /api/catalog/sync 요청.

    source 우선순위:
    - mode='github': repo_url + ref (GITHUB_PAT 필요)
    - mode='local': local_path (개발용)
    - mode='inline': manifest_yaml (테스트·CLI용)
    """

    service_code: str = Field(description="ops_services 등록·갱신 대상 코드")
    mode: str = Field(default="github", description="github / local / inline")
    repo_url: str | None = None
    ref: str = "main"
    local_path: str | None = None
    manifest_yaml: str | None = None


class SyncResponseDTO(BaseModel):
    service_code: str
    created: bool
    sections_added: list[str]
    sections_updated: list[str]
    sections_deleted: list[str]
    snapshot_id: int | None
    total_changes: int


# -- Health -----------------------------------------------------------------


class HealthSnapshotDTO(_OrmDTO):
    id: int
    section_id: int
    checked_at: datetime
    http_status: int | None
    latency_ms: int | None
    ok: bool
    error_text: str | None


class SectionHealthSummaryDTO(BaseModel):
    """섹션 카드/테이블에 표시할 최근 헬스 요약."""

    section_id: int
    last_checked_at: datetime | None = None
    last_ok: bool | None = None
    last_status: int | None = None
    last_latency_ms: int | None = None
    availability_24h: float | None = None  # 0.0~1.0
    samples_24h: int = 0


# -- Permissions / Assignment ----------------------------------------------


class AssignmentDTO(_OrmDTO):
    id: int
    section_id: int
    user_id: int
    user_email: str | None = None
    user_name: str | None = None
    can_edit_content: bool
    can_open_pr: bool
    can_publish: bool
    granted_at: datetime


class AssignmentRequest(BaseModel):
    section_id: int
    user_email: EmailStr
    can_edit_content: bool = False
    can_open_pr: bool = True
    can_publish: bool = False


# -- My sections ------------------------------------------------------------


class MySectionDTO(_OrmDTO):
    """`/api/my/sections` 단일 행 — 내가 owner / backup / 권한 부여된 섹션."""

    section_id: int
    service_code: str
    service_display_name: str
    section_code: str
    section_name: str
    level: str
    status: str
    route: str | None
    relation: str  # 'owner' / 'backup' / 'permission'
    health: SectionHealthSummaryDTO | None = None


# forward reference 해소
SectionDTO.model_rebuild()
