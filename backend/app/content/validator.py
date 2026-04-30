"""콘텐츠 블록 화이트리스트·길이·포맷 검증.

화이트리스트 정본: 가장 최신 ops_manifest_snapshots 의 sections[].content_blocks.
임의의 key 를 만들 수 없다 — 매니페스트 등록 → OpsConsole 사용 가능.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import OpsManifestSnapshot
from app.models.section import OpsSection


class ContentValidationError(ValueError):
    """매니페스트 화이트리스트 위반·길이 초과·잘못된 format."""


@dataclass(frozen=True)
class ContentBlockSpec:
    key: str
    format: str  # markdown / text / html
    max_length: int
    locales: list[str]
    description: str | None


async def fetch_block_spec(
    db: AsyncSession, section: OpsSection, key: str
) -> ContentBlockSpec:
    """매니페스트에서 (section.code, key) 의 블록 스펙을 가져온다.

    Raises:
        ContentValidationError: 섹션의 매니페스트 미존재, 또는 key 가 화이트리스트에 없음.
    """
    snap = (
        await db.execute(
            select(OpsManifestSnapshot)
            .where(OpsManifestSnapshot.service_id == section.service_id)
            .order_by(OpsManifestSnapshot.fetched_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if snap is None:
        raise ContentValidationError(
            f"service_id={section.service_id} 의 매니페스트 스냅샷이 없음"
        )

    sections = snap.manifest.get("sections", [])
    section_def = next((s for s in sections if s.get("code") == section.code), None)
    if section_def is None:
        raise ContentValidationError(
            f"매니페스트에 section '{section.code}' 가 없음 (스냅샷 갱신 필요)"
        )

    blocks = section_def.get("content_blocks") or []
    block_def = next((b for b in blocks if b.get("key") == key), None)
    if block_def is None:
        raise ContentValidationError(
            f"section '{section.code}' 에 content_block '{key}' 가 등록되지 않음 — "
            "매니페스트의 content_blocks 화이트리스트에 추가 필요"
        )

    return ContentBlockSpec(
        key=key,
        format=block_def.get("format", "markdown"),
        max_length=int(block_def.get("max_length", 5000)),
        locales=list(block_def.get("locales") or ["ko"]),
        description=block_def.get("description"),
    )


def assert_writable(spec: ContentBlockSpec, *, body: str | None, locale: str) -> None:
    """편집 시점 검증 — 길이 + locale + format(html 비활성)."""
    if locale not in spec.locales:
        raise ContentValidationError(
            f"locale '{locale}' 미허용 (허용: {spec.locales})"
        )
    if body is not None and len(body) > spec.max_length:
        raise ContentValidationError(
            f"본문 길이 {len(body)} 가 max_length {spec.max_length} 초과"
        )
    if spec.format == "html":
        # P3 단계는 html 모드 비활성 — sanitizer 가 안전성을 보장하기 전까진 차단
        raise ContentValidationError(
            "html format 은 P3 단계에서 비활성. markdown / text 만 허용"
        )
