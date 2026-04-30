"""P5 보안 강화 — SSRF guard, masking, audit API, security headers, role hierarchy."""
from __future__ import annotations

from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import masking
from app.core.security import role_at_least
from app.database.session import get_db
from app.jobs.url_guard import UnsafeURLError, assert_safe_probe_url
from app.main import app
from app.models.user import OpsUser


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
    return res.json()["access_token"]


# ---------------------------------------------------------------------------
# Role hierarchy (P5 §1)
# ---------------------------------------------------------------------------


def test_role_at_least_hierarchy():
    u = OpsUser(email="x", role="ops_admin")
    assert role_at_least(u, "ops_viewer") is True
    assert role_at_least(u, "ops_admin") is True

    m = OpsUser(email="y", role="ops_member")
    assert role_at_least(m, "ops_viewer") is True
    assert role_at_least(m, "ops_reviewer") is False
    assert role_at_least(m, "ops_admin") is False


# ---------------------------------------------------------------------------
# Masking (P5 §2)
# ---------------------------------------------------------------------------


def test_mask_email_short_local():
    assert masking.mask_email("ab@x.com") == "***@x.com"
    assert masking.mask_email("rainend00@gmail.com") == "rai***@gmail.com"
    assert masking.mask_email(None) is None
    assert masking.mask_email("notanemail") == "notanemail"


def test_mask_payload_redacts_tokens_and_emails():
    payload = {
        "user_email": "rainend00@gmail.com",
        "secret": "supersecret",
        "github_pat": "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        "session_token": "tok_short",
        "len": 1234,            # 면제
        "version": 7,
        "nested": {"password": "p", "name": "ok"},
        "items": [{"client_secret": "y"}, {"keep": "this"}],
    }
    masked = masking.mask_payload(payload)
    assert masked["user_email"] == "rai***@gmail.com"
    assert masked["secret"] == "***"
    assert "***" in masked["github_pat"] and masked["github_pat"] != payload["github_pat"]
    assert masked["session_token"] == "***"
    assert masked["len"] == 1234
    assert masked["version"] == 7
    assert masked["nested"]["password"] == "***"
    assert masked["nested"]["name"] == "ok"
    assert masked["items"][0]["client_secret"] == "***"
    assert masked["items"][1]["keep"] == "this"


# ---------------------------------------------------------------------------
# SSRF guard (P5 §6 A10)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/health",
    "http://localhost/health",  # 라이브 환경에서 localhost 가 127.0.0.1로 resolve
    "http://10.0.0.1/x",
    "http://192.168.1.1/x",
    "http://169.254.169.254/latest/meta-data/",
    "file:///etc/passwd",
    "gopher://example.com/x",
    "http://0.0.0.0/",
    "https://[::1]/",
])
def test_assert_safe_rejects_unsafe(url):
    with patch("app.jobs.url_guard.settings.app_debug", False):
        with patch("app.jobs.url_guard.settings.health_probe_allow_private", False):
            with pytest.raises(UnsafeURLError):
                assert_safe_probe_url(url)


def test_assert_safe_allows_public():
    with patch("app.jobs.url_guard.settings.app_debug", False):
        with patch("app.jobs.url_guard.settings.health_probe_allow_private", False):
            # 공개 도메인 + DNS resolve 후 사설 IP가 아닌 케이스
            assert_safe_probe_url("https://example.com/")


def test_assert_safe_dev_bypass():
    with patch("app.jobs.url_guard.settings.app_debug", True):
        with patch("app.jobs.url_guard.settings.health_probe_allow_private", True):
            assert_safe_probe_url("http://127.0.0.1/health")  # bypass


def test_assert_safe_empty_url():
    with pytest.raises(UnsafeURLError):
        assert_safe_probe_url("")


# ---------------------------------------------------------------------------
# Audit log API (P5 §2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_log_requires_admin(client: AsyncClient, db_session: AsyncSession):
    admin = await _login(client, "admin@example.com")
    member = await _login(client, "member@example.com")

    res = await client.get(
        "/api/audit-log",
        headers={"Authorization": f"Bearer {member}"},
    )
    assert res.status_code == 403

    res = await client.get(
        "/api/audit-log",
        headers={"Authorization": f"Bearer {admin}"},
    )
    assert res.status_code == 200
    rows = res.json()
    # 위 로그인 두 번이 audit log 에 user_login / user_created 로 기록됨
    assert len(rows) >= 1


@pytest.mark.asyncio
async def test_audit_log_email_masking(client: AsyncClient, db_session: AsyncSession):
    admin = await _login(client, "rainend00@gmail.com")
    res = await client.get(
        "/api/audit-log?action=user_created",
        headers={"Authorization": f"Bearer {admin}"},
    )
    assert res.status_code == 200
    rows = res.json()
    assert len(rows) >= 1
    # actor_email 마스킹
    if rows[0]["actor_email"]:
        assert "***" in rows[0]["actor_email"]
    # payload 의 email 도 마스킹
    payload = rows[0].get("payload") or {}
    if "email" in payload:
        assert "***" in payload["email"]


# ---------------------------------------------------------------------------
# Security headers (P5 §3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_security_headers_set_on_responses(client: AsyncClient):
    res = await client.get("/api/health")
    assert res.status_code == 200
    h = res.headers
    assert "content-security-policy" in h
    assert "x-frame-options" in h and h["x-frame-options"] == "DENY"
    assert "x-content-type-options" in h and h["x-content-type-options"] == "nosniff"
    assert "referrer-policy" in h
    assert "permissions-policy" in h
    # CSP 핵심 directive 존재
    csp = h["content-security-policy"]
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
