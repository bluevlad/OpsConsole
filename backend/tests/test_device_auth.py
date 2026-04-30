"""P4 디바이스 코드 OAuth — init/lookup/approve/poll E2E."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.main import app
from app.models.device_code import OpsDeviceCode


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


def _idinfo(email="user@example.com"):
    return {
        "iss": "https://accounts.google.com",
        "sub": "g-1",
        "email": email,
        "email_verified": True,
        "name": "U",
    }


async def _login(client: AsyncClient, email: str) -> str:
    with patch("app.api.auth.verify_google_id_token", return_value=_idinfo(email=email)):
        res = await client.post("/api/auth/google/verify", json={"credential": "x"})
    return res.json()["access_token"]


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_init_returns_codes_and_persists(client: AsyncClient, db_session: AsyncSession):
    res = await client.post(
        "/api/auth/device/init",
        json={"device_label": "MacBook Pro", "user_agent": "OpsConsole-Tray/0.1"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["device_code"]
    assert body["user_code"].count("-") == 1
    assert body["verification_uri"].endswith("/device")
    assert body["expires_in"] == 600

    row = (
        await db_session.execute(
            select(OpsDeviceCode).where(OpsDeviceCode.device_code == body["device_code"])
        )
    ).scalar_one()
    assert row.approved is False
    assert row.user_id is None
    assert row.device_label == "MacBook Pro"


# ---------------------------------------------------------------------------
# poll while pending
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_poll_pending_before_approval(client: AsyncClient):
    init = await client.post("/api/auth/device/init", json={})
    device_code = init.json()["device_code"]

    res = await client.post(
        "/api/auth/device/poll", json={"device_code": device_code}
    )
    assert res.status_code == 200
    assert res.json()["status"] == "pending"


@pytest.mark.asyncio
async def test_poll_unknown_device_code_404(client: AsyncClient):
    res = await client.post(
        "/api/auth/device/poll", json={"device_code": "no-such-code"}
    )
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# lookup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lookup_requires_auth(client: AsyncClient):
    init = await client.post(
        "/api/auth/device/init", json={"device_label": "tray"}
    )
    user_code = init.json()["user_code"]

    res = await client.get(f"/api/auth/device/lookup?user_code={user_code}")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_lookup_returns_metadata(client: AsyncClient):
    init = await client.post(
        "/api/auth/device/init", json={"device_label": "tray"}
    )
    user_code = init.json()["user_code"]
    token = await _login(client, "admin@example.com")

    res = await client.get(
        f"/api/auth/device/lookup?user_code={user_code}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["user_code"] == user_code
    assert body["device_label"] == "tray"
    assert body["approved"] is False


# ---------------------------------------------------------------------------
# approve + poll → token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approve_then_poll_returns_token(client: AsyncClient, db_session: AsyncSession):
    init = await client.post("/api/auth/device/init", json={"device_label": "tray"})
    device_code = init.json()["device_code"]
    user_code = init.json()["user_code"]

    token = await _login(client, "approver@example.com")

    res = await client.post(
        "/api/auth/device/approve",
        json={"user_code": user_code},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "approved"

    # poll → access_token 발급
    res = await client.post(
        "/api/auth/device/poll", json={"device_code": device_code}
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "approved"
    assert body["access_token"]
    assert body["user"]["email"] == "approver@example.com"

    # 다시 poll → 410 (한 번만 사용)
    res = await client.post(
        "/api/auth/device/poll", json={"device_code": device_code}
    )
    assert res.status_code == 410


# ---------------------------------------------------------------------------
# expiry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_poll_expired_returns_expired(client: AsyncClient, db_session: AsyncSession):
    init = await client.post("/api/auth/device/init", json={})
    device_code = init.json()["device_code"]

    # 강제 만료
    row = (
        await db_session.execute(
            select(OpsDeviceCode).where(OpsDeviceCode.device_code == device_code)
        )
    ).scalar_one()
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db_session.flush()

    res = await client.post(
        "/api/auth/device/poll", json={"device_code": device_code}
    )
    assert res.status_code == 200
    assert res.json()["status"] == "expired"


@pytest.mark.asyncio
async def test_approve_expired_410(client: AsyncClient, db_session: AsyncSession):
    init = await client.post("/api/auth/device/init", json={})
    user_code = init.json()["user_code"]

    row = (
        await db_session.execute(
            select(OpsDeviceCode).where(OpsDeviceCode.user_code == user_code)
        )
    ).scalar_one()
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db_session.flush()

    token = await _login(client, "u@example.com")
    res = await client.post(
        "/api/auth/device/approve",
        json={"user_code": user_code},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 410
