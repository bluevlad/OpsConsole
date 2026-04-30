"""P3 콘텐츠 블록 API + 워크플로 + 매니페스트 화이트리스트 + internal polling."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.main import app
from app.manifest.parser import parse_manifest
from app.manifest.sync import upsert_catalog
from app.models.permission import OpsSectionPermission
from app.models.section import OpsSection
from app.models.user import OpsUser

FIXTURE = Path(__file__).parent / "fixtures" / "allergyinsight-manifest.yml"


@pytest_asyncio.fixture
async def client(db_session: AsyncSession):
    async def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        try:
            yield ac
        finally:
            app.dependency_overrides.pop(get_db, None)


def _idinfo(email: str):
    return {
        "iss": "https://accounts.google.com",
        "sub": "g-1",
        "email": email,
        "email_verified": True,
        "name": email.split("@")[0],
    }


async def _login(client: AsyncClient, email: str) -> str:
    with patch("app.api.auth.verify_google_id_token", return_value=_idinfo(email=email)):
        res = await client.post("/api/auth/google/verify", json={"credential": "x"})
    assert res.status_code == 200
    return res.json()["access_token"]


async def _seed(db: AsyncSession) -> OpsSection:
    text = FIXTURE.read_text(encoding="utf-8")
    await upsert_catalog(db, parse_manifest(text), ref="test")
    return (
        await db.execute(select(OpsSection).where(OpsSection.code == "ai-consult"))
    ).scalar_one()


async def _grant_perm(
    db: AsyncSession, *, user_email: str, section_id: int, edit=False, publish=False
):
    user = (
        await db.execute(select(OpsUser).where(OpsUser.email == user_email))
    ).scalar_one()
    db.add(
        OpsSectionPermission(
            section_id=section_id,
            user_id=user.id,
            can_edit_content=edit,
            can_publish=publish,
            can_open_pr=True,
        )
    )
    await db.flush()


# ----------------------- list whitelist + draft -------------------------


@pytest.mark.asyncio
async def test_list_blocks_returns_manifest_whitelist(
    client: AsyncClient, db_session: AsyncSession
):
    section = await _seed(db_session)
    token = await _login(client, "viewer@example.com")

    res = await client.get(
        "/api/content/sections/allergyinsight/ai-consult/blocks",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    rows = res.json()
    # AllergyInsight ai-consult 매니페스트의 content_blocks 1개 (intro_banner)
    assert len(rows) == 1
    assert rows[0]["spec"]["key"] == "ai_consult.intro_banner"
    assert rows[0]["block"] is None  # 아직 row 없음


@pytest.mark.asyncio
async def test_save_draft_requires_can_edit(
    client: AsyncClient, db_session: AsyncSession
):
    section = await _seed(db_session)
    # 첫 가입자가 ops_admin 되므로 admin 자리를 먼저 채워둔다
    await _login(client, "admin@example.com")
    member = await _login(client, "member@example.com")

    body = {"body": "## 안내\n새로운 배너", "locale": "ko"}
    # 권한 없음 → 403
    res = await client.put(
        "/api/content/sections/allergyinsight/ai-consult/blocks/ai_consult.intro_banner/draft",
        headers={"Authorization": f"Bearer {member}"},
        json=body,
    )
    assert res.status_code == 403

    # 권한 부여 후 200
    await _grant_perm(db_session, user_email="member@example.com", section_id=section.id, edit=True)
    res = await client.put(
        "/api/content/sections/allergyinsight/ai-consult/blocks/ai_consult.intro_banner/draft",
        headers={"Authorization": f"Bearer {member}"},
        json=body,
    )
    assert res.status_code == 200, res.text
    block = res.json()
    assert block["status"] == "draft"
    assert block["draft_body"] == body["body"]
    assert block["spec"]["max_length"] == 2000


@pytest.mark.asyncio
async def test_save_draft_rejects_unknown_key(
    client: AsyncClient, db_session: AsyncSession
):
    section = await _seed(db_session)
    admin = await _login(client, "admin@example.com")  # 첫 사용자 → ops_admin

    res = await client.put(
        "/api/content/sections/allergyinsight/ai-consult/blocks/ai_consult.unknown_key/draft",
        headers={"Authorization": f"Bearer {admin}"},
        json={"body": "x", "locale": "ko"},
    )
    assert res.status_code == 422
    assert "content_block" in res.text.lower() or "unknown_key" in res.text


@pytest.mark.asyncio
async def test_save_draft_rejects_too_long(
    client: AsyncClient, db_session: AsyncSession
):
    section = await _seed(db_session)
    admin = await _login(client, "admin@example.com")

    big = "x" * 3000  # max_length=2000 초과
    res = await client.put(
        "/api/content/sections/allergyinsight/ai-consult/blocks/ai_consult.intro_banner/draft",
        headers={"Authorization": f"Bearer {admin}"},
        json={"body": big, "locale": "ko"},
    )
    assert res.status_code == 422


# ----------------------- workflow ---------------------------------------


@pytest.mark.asyncio
async def test_full_workflow_draft_review_approve_published(
    client: AsyncClient, db_session: AsyncSession
):
    section = await _seed(db_session)
    admin = await _login(client, "admin@example.com")  # ops_admin: 모든 권한

    # 1) draft
    res = await client.put(
        "/api/content/sections/allergyinsight/ai-consult/blocks/ai_consult.intro_banner/draft",
        headers={"Authorization": f"Bearer {admin}"},
        json={"body": "v1 본문", "locale": "ko"},
    )
    assert res.status_code == 200
    block_id = res.json()["id"]

    # 2) request review
    res = await client.post(
        f"/api/content/blocks/{block_id}/request-review",
        headers={"Authorization": f"Bearer {admin}"},
        json={},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "pending_review"

    # 3) approve → published
    res = await client.post(
        f"/api/content/blocks/{block_id}/approve",
        headers={"Authorization": f"Bearer {admin}"},
        json={"note": "good"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "published"
    assert body["published_body"] == "v1 본문"
    assert body["published_version"] == 1

    # 4) versions
    res = await client.get(
        f"/api/content/blocks/{block_id}/versions",
        headers={"Authorization": f"Bearer {admin}"},
    )
    assert res.status_code == 200
    versions = res.json()
    assert len(versions) == 1
    assert versions[0]["version"] == 1


@pytest.mark.asyncio
async def test_reject_returns_to_draft(client: AsyncClient, db_session: AsyncSession):
    section = await _seed(db_session)
    admin = await _login(client, "admin@example.com")

    res = await client.put(
        "/api/content/sections/allergyinsight/ai-consult/blocks/ai_consult.intro_banner/draft",
        headers={"Authorization": f"Bearer {admin}"},
        json={"body": "x", "locale": "ko"},
    )
    block_id = res.json()["id"]
    await client.post(
        f"/api/content/blocks/{block_id}/request-review",
        headers={"Authorization": f"Bearer {admin}"},
        json={},
    )
    res = await client.post(
        f"/api/content/blocks/{block_id}/reject",
        headers={"Authorization": f"Bearer {admin}"},
        json={"note": "어투 수정 필요"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "draft"
    assert body["review_note"] == "어투 수정 필요"
    assert body["published_version"] == 0


@pytest.mark.asyncio
async def test_publish_directly_increments_version(
    client: AsyncClient, db_session: AsyncSession
):
    section = await _seed(db_session)
    admin = await _login(client, "admin@example.com")

    # v1
    res = await client.put(
        "/api/content/sections/allergyinsight/ai-consult/blocks/ai_consult.intro_banner/draft",
        headers={"Authorization": f"Bearer {admin}"},
        json={"body": "v1", "locale": "ko"},
    )
    block_id = res.json()["id"]
    res = await client.post(
        f"/api/content/blocks/{block_id}/publish",
        headers={"Authorization": f"Bearer {admin}"},
    )
    assert res.json()["published_version"] == 1

    # v2 (재편집 → 직접 게시)
    await client.put(
        "/api/content/sections/allergyinsight/ai-consult/blocks/ai_consult.intro_banner/draft",
        headers={"Authorization": f"Bearer {admin}"},
        json={"body": "v2", "locale": "ko"},
    )
    res = await client.post(
        f"/api/content/blocks/{block_id}/publish",
        headers={"Authorization": f"Bearer {admin}"},
    )
    assert res.json()["published_version"] == 2
    assert res.json()["published_body"] == "v2"


# ----------------------- internal polling endpoint ----------------------


@pytest.mark.asyncio
async def test_internal_endpoint_returns_published_only(
    client: AsyncClient, db_session: AsyncSession
):
    section = await _seed(db_session)
    admin = await _login(client, "admin@example.com")

    # 1개 게시
    res = await client.put(
        "/api/content/sections/allergyinsight/ai-consult/blocks/ai_consult.intro_banner/draft",
        headers={"Authorization": f"Bearer {admin}"},
        json={"body": "공개된 배너", "locale": "ko"},
    )
    block_id = res.json()["id"]
    await client.post(
        f"/api/content/blocks/{block_id}/publish",
        headers={"Authorization": f"Bearer {admin}"},
    )

    # internal endpoint
    with patch("app.api.internal_content.settings.ops_internal_token", "secret-token"):
        res = await client.get(
            "/api/internal/content/published?service=allergyinsight",
            headers={"X-Ops-Internal-Token": "secret-token"},
        )
    assert res.status_code == 200
    body = res.json()
    assert "allergyinsight" in body
    section_data = body["allergyinsight"]["ai-consult"]
    assert "ai_consult.intro_banner" in section_data
    block = section_data["ai_consult.intro_banner"]["ko"]
    assert block["body"] == "공개된 배너"
    assert block["version"] == 1
    assert "published_at" in block

    # ETag 동작
    etag = res.headers["etag"]
    with patch("app.api.internal_content.settings.ops_internal_token", "secret-token"):
        res2 = await client.get(
            "/api/internal/content/published?service=allergyinsight",
            headers={"X-Ops-Internal-Token": "secret-token", "If-None-Match": etag},
        )
    assert res2.status_code == 304


@pytest.mark.asyncio
async def test_internal_endpoint_token_required(client: AsyncClient):
    with patch("app.api.internal_content.settings.ops_internal_token", "secret"):
        # 토큰 없음
        res = await client.get("/api/internal/content/published")
        assert res.status_code == 401
        # 잘못된 토큰
        res = await client.get(
            "/api/internal/content/published",
            headers={"X-Ops-Internal-Token": "wrong"},
        )
        assert res.status_code == 401
