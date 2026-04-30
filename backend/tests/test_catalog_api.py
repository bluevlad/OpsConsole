"""GET /api/catalog/* + POST /api/catalog/sync 엔드포인트 테스트.

실 opsconsole_dev DB의 트랜잭션을 시작·rollback 격리하기 위해
get_db dependency를 conftest의 db_session으로 override 한다.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.main import app

FIXTURE = Path(__file__).parent / "fixtures" / "allergyinsight-manifest.yml"


@pytest.fixture
def client(db_session: AsyncSession):
    """get_db override + httpx AsyncClient. db_session은 conftest의 rollback fixture."""

    async def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    try:
        yield AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_list_services_empty(client: AsyncClient):
    async with client as c:
        res = await c.get("/api/catalog/services")
    assert res.status_code == 200
    assert res.json() == []


@pytest.mark.asyncio
async def test_sync_inline_creates_service_and_lists(client: AsyncClient):
    yaml_text = FIXTURE.read_text(encoding="utf-8")
    async with client as c:
        # 1) sync inline (mode=inline 으로 GitHub 의존 제거)
        res = await c.post(
            "/api/catalog/sync",
            json={
                "service_code": "allergyinsight",
                "mode": "inline",
                "manifest_yaml": yaml_text,
                "ref": "test",
            },
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["created"] is True
        assert len(body["sections_added"]) == 11
        assert body["total_changes"] == 11

        # 2) services 목록
        res = await c.get("/api/catalog/services")
        assert res.status_code == 200
        services = res.json()
        assert len(services) == 1
        assert services[0]["code"] == "allergyinsight"
        assert services[0]["section_count"] == 11

        # 3) sections 목록
        res = await c.get("/api/catalog/services/allergyinsight/sections")
        assert res.status_code == 200
        sections = res.json()
        assert len(sections) == 11
        ai_consult = next(s for s in sections if s["code"] == "ai-consult")
        # ai-consult 자산: frontend 1 + backend_router 1 + service 1 + table 2 + endpoint 3 = 8
        assert len(ai_consult["assets"]) == 8

        # 4) 단일 section
        res = await c.get(
            "/api/catalog/services/allergyinsight/sections/ai-consult"
        )
        assert res.status_code == 200
        section = res.json()
        assert section["level"] == "public"
        assert section["owner_email"] == "rainend00@gmail.com"


@pytest.mark.asyncio
async def test_get_service_404(client: AsyncClient):
    async with client as c:
        res = await c.get("/api/catalog/services/nonexistent")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_sync_rejects_service_code_mismatch(client: AsyncClient):
    yaml_text = FIXTURE.read_text(encoding="utf-8")
    async with client as c:
        res = await c.post(
            "/api/catalog/sync",
            json={
                "service_code": "wrong-code",
                "mode": "inline",
                "manifest_yaml": yaml_text,
            },
        )
    assert res.status_code == 400
    assert "service" in res.text.lower()


@pytest.mark.asyncio
async def test_sync_rejects_invalid_manifest(client: AsyncClient):
    async with client as c:
        res = await c.post(
            "/api/catalog/sync",
            json={
                "service_code": "x",
                "mode": "inline",
                "manifest_yaml": "version: '1.0'\nservice: x\n",  # display_name + sections 누락
            },
        )
    assert res.status_code == 422
