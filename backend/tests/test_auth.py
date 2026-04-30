"""POST /api/auth/google/verify, GET /api/auth/me — verifier 모킹 후 라우터 검증."""
from __future__ import annotations

from collections.abc import AsyncGenerator
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.main import app
from app.models.user import OpsUser


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        try:
            yield ac
        finally:
            app.dependency_overrides.pop(get_db, None)


def _fake_idinfo(email: str = "rainend00@gmail.com", name: str = "Rainend"):
    return {
        "iss": "https://accounts.google.com",
        "sub": "google-sub-123",
        "email": email,
        "email_verified": True,
        "name": name,
    }


@pytest.mark.asyncio
async def test_first_user_becomes_ops_admin(client: AsyncClient, db_session: AsyncSession):
    with patch("app.api.auth.verify_google_id_token", return_value=_fake_idinfo()):
        res = await client.post(
            "/api/auth/google/verify", json={"credential": "fake-id-token"}
        )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == "rainend00@gmail.com"
    assert body["user"]["role"] == "ops_admin"  # 첫 가입자
    assert body["access_token"]

    user = (
        await db_session.execute(select(OpsUser).where(OpsUser.email == "rainend00@gmail.com"))
    ).scalar_one()
    assert user.role == "ops_admin"
    assert user.last_login_at is not None


@pytest.mark.asyncio
async def test_second_user_is_ops_member(client: AsyncClient):
    with patch("app.api.auth.verify_google_id_token", return_value=_fake_idinfo()):
        await client.post("/api/auth/google/verify", json={"credential": "x"})

    with patch(
        "app.api.auth.verify_google_id_token",
        return_value=_fake_idinfo(email="second@example.com", name="Second"),
    ):
        res = await client.post("/api/auth/google/verify", json={"credential": "y"})
    assert res.status_code == 200, res.text
    assert res.json()["user"]["role"] == "ops_member"


@pytest.mark.asyncio
async def test_existing_user_login_updates_last_login(client: AsyncClient):
    with patch("app.api.auth.verify_google_id_token", return_value=_fake_idinfo()):
        res1 = await client.post("/api/auth/google/verify", json={"credential": "x"})
        res2 = await client.post("/api/auth/google/verify", json={"credential": "y"})
    assert res1.status_code == 200
    assert res2.status_code == 200
    assert res1.json()["user"]["id"] == res2.json()["user"]["id"]


@pytest.mark.asyncio
async def test_me_returns_current_user(client: AsyncClient):
    with patch("app.api.auth.verify_google_id_token", return_value=_fake_idinfo()):
        login = await client.post("/api/auth/google/verify", json={"credential": "x"})
    token = login.json()["access_token"]

    res = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    body = res.json()
    assert body["email"] == "rainend00@gmail.com"
    assert body["role"] == "ops_admin"


@pytest.mark.asyncio
async def test_me_without_token_401(client: AsyncClient):
    res = await client.get("/api/auth/me")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_me_with_invalid_token_401(client: AsyncClient):
    res = await client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert res.status_code == 401
