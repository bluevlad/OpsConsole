"""publish_block — 드래프트 → 게시 전이 + 버전 INSERT.

호출자가 트랜잭션 경계 제어. 본 함수는 commit 안 함.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import OpsContentBlock, OpsContentBlockVersion
from app.models.user import OpsUser


async def publish_block(
    db: AsyncSession,
    block: OpsContentBlock,
    *,
    publisher: OpsUser,
) -> OpsContentBlockVersion:
    """draft_body 를 published 로 승격 + 버전 INSERT.

    전제: 호출자가 status='pending_review' 또는 'draft' 인지 확인 + 권한 검사.
    """
    if block.draft_body is None:
        raise ValueError("draft_body 가 비어있습니다 — 게시 불가")

    new_version = (block.published_version or 0) + 1
    snapshot = OpsContentBlockVersion(
        block_id=block.id,
        version=new_version,
        body=block.draft_body,
        edited_by=publisher.id,
    )
    db.add(snapshot)

    block.published_body = block.draft_body
    block.published_version = new_version
    block.published_by = publisher.id
    block.published_at = datetime.now(timezone.utc)
    block.status = "published"
    # 게시 후 draft 는 published 와 동일 — 다음 편집을 위해 그대로 둔다 (UI 상 '변경 없음')

    await db.flush()
    return snapshot
