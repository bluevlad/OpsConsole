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


# -- Change Requests (P2) --------------------------------------------------


class AttachmentDTO(BaseModel):
    filename: str
    url: str | None = None
    size: int | None = None


class ChangeRequestDTO(_OrmDTO):
    id: int
    section_id: int | None
    section_code: str | None = None
    service_code: str | None = None
    requester_id: int
    requester_email: str | None = None
    title: str
    description_md: str | None
    status: str
    priority: str
    github_issue_url: str | None
    github_issue_number: int | None
    github_pr_url: str | None
    github_pr_number: int | None
    attachments: list[AttachmentDTO] | None
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None


class ChangeRequestCreateRequest(BaseModel):
    """변경요청 신규 발급. section_id 가 있으면 GitHub Issue 자동 생성."""

    section_id: int | None = None
    title: str = Field(min_length=1, max_length=200)
    description_md: str | None = None
    priority: str = Field(default="normal", pattern=r"^(low|normal|high|urgent)$")
    attachments: list[AttachmentDTO] | None = None
    skip_github: bool = False  # True 면 Issue 발급 생략 (테스트/dry-run)


class ChangeRequestPatchRequest(BaseModel):
    title: str | None = None
    description_md: str | None = None
    priority: str | None = Field(default=None, pattern=r"^(low|normal|high|urgent)$")
    status: str | None = Field(
        default=None, pattern=r"^(submitted|in_pr|merged|closed|rejected)$"
    )


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


# -- Content Blocks (P3) ---------------------------------------------------


class ContentBlockSpecDTO(BaseModel):
    """매니페스트 화이트리스트 항목 (편집 화면에서 max_length/locales 표시)."""

    key: str
    format: str
    max_length: int
    locales: list[str]
    description: str | None = None


class ContentBlockDTO(_OrmDTO):
    id: int
    section_id: int
    section_code: str | None = None
    service_code: str | None = None
    key: str
    locale: str
    format: str
    draft_body: str | None
    draft_edited_by: int | None
    draft_edited_at: datetime | None
    published_body: str | None
    published_version: int
    published_by: int | None
    published_at: datetime | None
    status: str
    reviewer_id: int | None
    review_note: str | None
    spec: ContentBlockSpecDTO | None = None


class ContentBlockListItemDTO(BaseModel):
    """매니페스트의 화이트리스트 + DB row 매칭 (없으면 block=None)."""

    spec: ContentBlockSpecDTO
    block: ContentBlockDTO | None = None


class DraftSaveRequest(BaseModel):
    body: str
    locale: str = "ko"


class ReviewRequest(BaseModel):
    reviewer_email: EmailStr | None = None


class ReviewDecisionRequest(BaseModel):
    note: str | None = None


# forward reference 해소
SectionDTO.model_rebuild()
