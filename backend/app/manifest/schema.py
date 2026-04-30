"""OpsConsole 매니페스트 Pydantic 스키마 (v1.0).

스키마 정본:
    Claude-Opus-bluevlad/standards/ops-console/manifest-schema.yml

후방호환만 허용 — 필드 추가 ✅, 삭제·이름 변경 ❌. 비호환 변경은 v2.0 분기.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl, field_validator

# -- 공통 패턴 ---------------------------------------------------------------

CODE_PATTERN = r"^[a-z][a-z0-9-]*$"            # service / section code
SLACK_PATTERN = r"^#[a-z0-9-]+$"               # slack channel
CONTENT_KEY_PATTERN = r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$"  # {section}.{block}


class _StrictModel(BaseModel):
    """Reject unknown keys — manifest 작성 오타 조기 발견."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_default=True,
    )


# -- 하위 모델 ---------------------------------------------------------------


class Contact(_StrictModel):
    primary_owner: EmailStr | None = None
    backup_owner: EmailStr | None = None
    slack_channel: str | None = Field(default=None, pattern=SLACK_PATTERN)


class PublishEndpoint(_StrictModel):
    mode: Literal["polling", "webhook"] = "polling"
    webhook_url: HttpUrl | None = None
    polling_endpoint: str = "/api/internal/content/published"
    auth_header: str = "X-Ops-Internal-Token"


class SectionAssets(_StrictModel):
    frontend: list[str] = Field(default_factory=list)
    backend_router: list[str] = Field(default_factory=list)
    service: list[str] = Field(default_factory=list)
    models: list[str] = Field(default_factory=list)
    tables: list[str] = Field(default_factory=list)
    endpoints: list[str] = Field(default_factory=list)


class SectionHealth(_StrictModel):
    url: HttpUrl | None = None
    api: str | None = None
    method: Literal["GET", "HEAD", "POST"] = "GET"
    timeout_ms: int = Field(default=5000, ge=1000, le=30000)
    expected_status: int = 200


class ContentBlock(_StrictModel):
    key: str = Field(pattern=CONTENT_KEY_PATTERN)
    format: Literal["markdown", "text", "html"] = "markdown"
    max_length: int = 5000
    locales: list[str] = Field(default_factory=lambda: ["ko"])
    description: str | None = None


class Section(_StrictModel):
    code: str = Field(pattern=CODE_PATTERN)
    name: str
    level: Literal["public", "member", "admin"]
    route: str | None = None
    external: bool = False
    status: Literal["live", "beta", "deprecated", "planned"] = "live"
    owner: EmailStr | None = None
    backup: EmailStr | None = None
    description: str | None = None
    assets: SectionAssets = Field(default_factory=SectionAssets)
    health: SectionHealth | None = None
    content_blocks: list[ContentBlock] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


# -- 루트 모델 ---------------------------------------------------------------


class Manifest(_StrictModel):
    """ops/manifest.yml 루트."""

    version: Literal["1.0"]
    service: str = Field(pattern=CODE_PATTERN)
    display_name: str
    gateway_url: HttpUrl | None = None
    repo_url: HttpUrl | None = None
    contact: Contact | None = None
    sections: list[Section] = Field(min_length=1)
    publish_endpoint: PublishEndpoint | None = None

    @field_validator("sections")
    @classmethod
    def _unique_section_codes(cls, sections: list[Section]) -> list[Section]:
        codes = [s.code for s in sections]
        if len(codes) != len(set(codes)):
            seen, dups = set(), set()
            for c in codes:
                (dups if c in seen else seen).add(c)
            raise ValueError(f"sections 코드 중복: {sorted(dups)}")
        return sections


__all__ = [
    "Contact",
    "ContentBlock",
    "Manifest",
    "PublishEndpoint",
    "Section",
    "SectionAssets",
    "SectionHealth",
]
