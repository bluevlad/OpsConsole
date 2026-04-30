"""P1 API: /api/my/sections + /api/assignments + /api/health/* — 라우터 검증."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
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
from app.models.health import OpsHealthSnapshot
from app.models.permission import OpsSectionPermission
from app.models.section import OpsSection
from app.models.service import OpsService
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


def _idinfo(email="rainend00@gmail.com", name="Owner"):
    return {
        "iss": "https://accounts.google.com",
        "sub": "g-1",
        "email": email,
        "email_verified": True,
        "name": name,
    }


async def _login_as(client: AsyncClient, email: str) -> str:
    """첫 로그인이면 ops_admin, 아니면 ops_member. JWT 반환."""
    with patch("app.api.auth.verify_google_id_token", return_value=_idinfo(email=email)):
        res = await client.post("/api/auth/google/verify", json={"credential": "x"})
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


async def _seed_allergyinsight(db_session: AsyncSession) -> OpsService:
    text = FIXTURE.read_text(encoding="utf-8")
    manifest = parse_manifest(text)
    await upsert_catalog(db_session, manifest, ref="test")
    await db_session.commit()
    svc = (
        await db_session.execute(select(OpsService).where(OpsService.code == "allergyinsight"))
    ).scalar_one()
    return svc


# -- /api/my/sections -------------------------------------------------------


@pytest.mark.asyncio
async def test_my_sections_owner_relation(client: AsyncClient, db_session: AsyncSession):
    """매니페스트 owner=rainend00@gmail.com 인 섹션이 11개 모두 표시."""
    await _seed_allergyinsight(db_session)
    token = await _login_as(client, "rainend00@gmail.com")

    res = await client.get(
        "/api/my/sections", headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 200
    rows = res.json()
    # AllergyInsight 시드 매니페스트의 owner 필드는 모두 rainend00@gmail.com
    assert len(rows) == 11
    assert all(r["relation"] == "owner" for r in rows)
    assert all(r["service_code"] == "allergyinsight" for r in rows)
    # health 는 시계열이 없으므로 None 허용 (samples_24h=0)
    for r in rows:
        assert r["health"]["samples_24h"] == 0


@pytest.mark.asyncio
async def test_my_sections_permission_relation(client: AsyncClient, db_session: AsyncSession):
    """owner 가 아닌 사용자는 owner 섹션 없음. 권한 부여 시 'permission' 으로 보임."""
    svc = await _seed_allergyinsight(db_session)
    section = (
        await db_session.execute(
            select(OpsSection).where(
                OpsSection.service_id == svc.id, OpsSection.code == "ai-consult"
            )
        )
    ).scalar_one()

    token = await _login_as(client, "other@example.com")
    user = (
        await db_session.execute(select(OpsUser).where(OpsUser.email == "other@example.com"))
    ).scalar_one()
    db_session.add(
        OpsSectionPermission(
            section_id=section.id, user_id=user.id, can_open_pr=True
        )
    )
    await db_session.flush()

    res = await client.get(
        "/api/my/sections", headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 200
    rows = res.json()
    assert len(rows) == 1
    assert rows[0]["section_code"] == "ai-consult"
    assert rows[0]["relation"] == "permission"


@pytest.mark.asyncio
async def test_my_sections_unauthenticated_401(client: AsyncClient):
    res = await client.get("/api/my/sections")
    assert res.status_code == 401


# -- /api/assignments -------------------------------------------------------


@pytest.mark.asyncio
async def test_assignment_create_requires_admin(client: AsyncClient, db_session: AsyncSession):
    """첫 사용자(ops_admin) → OK. 두번째(ops_member) → 403."""
    await _seed_allergyinsight(db_session)
    section = (
        await db_session.execute(
            select(OpsSection).where(OpsSection.code == "ai-consult")
        )
    ).scalar_one()

    admin_token = await _login_as(client, "admin@example.com")
    member_token = await _login_as(client, "member@example.com")

    body = {"section_id": section.id, "user_email": "x@example.com"}

    # member → 403
    res = await client.post(
        "/api/assignments",
        json=body,
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert res.status_code == 403

    # admin → 201
    res = await client.post(
        "/api/assignments",
        json=body,
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 201
    created = res.json()
    assert created["section_id"] == section.id
    assert created["user_email"] == "x@example.com"
    assert created["can_open_pr"] is True

    # placeholder user 가 생성됐는지
    placeholder = (
        await db_session.execute(select(OpsUser).where(OpsUser.email == "x@example.com"))
    ).scalar_one()
    assert placeholder.role == "ops_member"


@pytest.mark.asyncio
async def test_assignment_update_then_revoke(client: AsyncClient, db_session: AsyncSession):
    await _seed_allergyinsight(db_session)
    section = (
        await db_session.execute(select(OpsSection).where(OpsSection.code == "newsletter"))
    ).scalar_one()
    admin_token = await _login_as(client, "admin@example.com")

    body = {
        "section_id": section.id,
        "user_email": "y@example.com",
        "can_edit_content": False,
    }

    # 1차 create
    res = await client.post(
        "/api/assignments", json=body, headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert res.status_code == 201
    aid = res.json()["id"]

    # 2차 update (can_edit_content=true)
    body["can_edit_content"] = True
    res = await client.post(
        "/api/assignments", json=body, headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert res.status_code == 201
    assert res.json()["id"] == aid  # 동일 row upsert
    assert res.json()["can_edit_content"] is True

    # 3차 revoke
    res = await client.delete(
        f"/api/assignments/{aid}", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert res.status_code == 204

    perm = (
        await db_session.execute(
            select(OpsSectionPermission).where(OpsSectionPermission.id == aid)
        )
    ).scalar_one_or_none()
    assert perm is None


# -- /api/health/snapshots --------------------------------------------------


@pytest.mark.asyncio
async def test_health_snapshots_returns_recent(client: AsyncClient, db_session: AsyncSession):
    svc = await _seed_allergyinsight(db_session)
    section = (
        await db_session.execute(
            select(OpsSection).where(OpsSection.service_id == svc.id, OpsSection.code == "ai-consult")
        )
    ).scalar_one()

    now = datetime.now(timezone.utc)
    db_session.add_all(
        [
            OpsHealthSnapshot(
                section_id=section.id,
                checked_at=now - timedelta(minutes=10),
                http_status=200,
                latency_ms=120,
                ok=True,
            ),
            OpsHealthSnapshot(
                section_id=section.id,
                checked_at=now - timedelta(minutes=5),
                http_status=503,
                latency_ms=200,
                ok=False,
                error_text="503 Service Unavailable",
            ),
        ]
    )
    await db_session.flush()

    token = await _login_as(client, "viewer@example.com")
    res = await client.get(
        "/api/health/snapshots/allergyinsight/ai-consult",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    rows = res.json()
    assert len(rows) == 2
    # 최신순 정렬
    assert rows[0]["http_status"] == 503
    assert rows[1]["http_status"] == 200

    # summary
    res = await client.get(
        "/api/health/summary/allergyinsight/ai-consult",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    summary = res.json()
    assert summary["last_status"] == 503
    assert summary["last_ok"] is False
    assert summary["samples_24h"] == 2
    # 1 ok / 2 total = 0.5
    assert summary["availability_24h"] == 0.5


@pytest.mark.asyncio
async def test_health_snapshot_404(client: AsyncClient, db_session: AsyncSession):
    await _seed_allergyinsight(db_session)
    token = await _login_as(client, "viewer@example.com")
    res = await client.get(
        "/api/health/snapshots/allergyinsight/nope",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 404
