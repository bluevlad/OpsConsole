"""API 응답 DTO — ORM 직렬화 / 매니페스트 sync 결과."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


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
