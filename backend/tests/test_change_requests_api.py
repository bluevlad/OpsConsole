"""POST/GET/PATCH /api/change-requests + 웹훅 endpoint."""
from __future__ import annotations

import hashlib
import hmac
import json
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
from app.models.change_request import OpsChangeRequest
from app.models.section import OpsSection

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


def _idinfo(email="user@example.com", name="User"):
    return {
        "iss": "https://accounts.google.com",
        "sub": "g-1",
        "email": email,
        "email_verified": True,
        "name": name,
    }


async def _login(client: AsyncClient, email: str) -> str:
    with patch("app.api.auth.verify_google_id_token", return_value=_idinfo(email=email)):
        res = await client.post("/api/auth/google/verify", json={"credential": "x"})
    assert res.status_code == 200
    return res.json()["access_token"]


async def _seed(db_session: AsyncSession) -> OpsSection:
    text = FIXTURE.read_text(encoding="utf-8")
    await upsert_catalog(db_session, parse_manifest(text), ref="test")
    return (
        await db_session.execute(select(OpsSection).where(OpsSection.code == "ai-consult"))
    ).scalar_one()


# ---------------------------------------------------------------------------
# create + GitHub Issue 자동 발급 (mock)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_with_github_issue_auto_open(
    client: AsyncClient, db_session: AsyncSession
):
    sec = await _seed(db_session)
    token = await _login(client, "user@example.com")

    fake_issue = {
        "number": 7,
        "html_url": "https://github.com/bluevlad/AllergyInsight/issues/7",
    }

    with patch("app.api.change_requests.gh_client.create_issue", return_value=fake_issue) as mock:
        res = await client.post(
            "/api/change-requests",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "section_id": sec.id,
                "title": "AI 상담 페이지 배너 수정",
                "description_md": "친근한 어투로 변경",
                "priority": "high",
            },
        )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["status"] == "submitted"
    assert body["github_issue_number"] == 7
    assert body["github_issue_url"] == fake_issue["html_url"]
    assert body["section_code"] == "ai-consult"
    assert body["service_code"] == "allergyinsight"

    # GitHub 호출 인자 검증
    mock.assert_called_once()
    args, kwargs = mock.call_args
    assert args[0] == "https://github.com/bluevlad/AllergyInsight"
    assert kwargs["title"] == "[ops:ai-consult] AI 상담 페이지 배너 수정"
    assert "from:ops-console" in kwargs["labels"]
    assert "section:ai-consult" in kwargs["labels"]
    assert "priority:high" in kwargs["labels"]


@pytest.mark.asyncio
async def test_create_skip_github(client: AsyncClient, db_session: AsyncSession):
    sec = await _seed(db_session)
    token = await _login(client, "user@example.com")

    with patch("app.api.change_requests.gh_client.create_issue") as mock:
        res = await client.post(
            "/api/change-requests",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "section_id": sec.id,
                "title": "test",
                "skip_github": True,
            },
        )
    assert res.status_code == 201
    assert res.json()["github_issue_number"] is None
    mock.assert_not_called()


@pytest.mark.asyncio
async def test_create_handles_github_error_gracefully(
    client: AsyncClient, db_session: AsyncSession
):
    """GitHub 호출 실패해도 변경요청 자체는 생성되어야 함 (이슈 발급 실패 이벤트만 기록)."""
    from app.github.client import GitHubError

    sec = await _seed(db_session)
    token = await _login(client, "user@example.com")

    with patch(
        "app.api.change_requests.gh_client.create_issue",
        side_effect=GitHubError("403 rate limited"),
    ):
        res = await client.post(
            "/api/change-requests",
            headers={"Authorization": f"Bearer {token}"},
            json={"section_id": sec.id, "title": "x"},
        )
    assert res.status_code == 201
    body = res.json()
    assert body["github_issue_number"] is None


# ---------------------------------------------------------------------------
# list + filter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_filter_mine_and_status(client: AsyncClient, db_session: AsyncSession):
    sec = await _seed(db_session)
    a_token = await _login(client, "alice@example.com")
    b_token = await _login(client, "bob@example.com")

    with patch(
        "app.api.change_requests.gh_client.create_issue",
        return_value={"number": 1, "html_url": "x"},
    ):
        for token in (a_token, a_token, b_token):
            res = await client.post(
                "/api/change-requests",
                headers={"Authorization": f"Bearer {token}"},
                json={"section_id": sec.id, "title": "t", "skip_github": True},
            )
            assert res.status_code == 201

    # alice 만
    res = await client.get(
        "/api/change-requests",
        params={"mine": True},
        headers={"Authorization": f"Bearer {a_token}"},
    )
    assert res.status_code == 200
    assert len(res.json()) == 2

    # 전체
    res = await client.get(
        "/api/change-requests",
        headers={"Authorization": f"Bearer {a_token}"},
    )
    assert len(res.json()) == 3

    # status=submitted
    res = await client.get(
        "/api/change-requests",
        params={"status": "submitted"},
        headers={"Authorization": f"Bearer {a_token}"},
    )
    assert all(r["status"] == "submitted" for r in res.json())


# ---------------------------------------------------------------------------
# patch (status 변경은 ops_admin 만)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_status_requires_admin(client: AsyncClient, db_session: AsyncSession):
    sec = await _seed(db_session)
    admin_token = await _login(client, "admin@example.com")  # 첫 사용자 → ops_admin
    member_token = await _login(client, "member@example.com")

    res = await client.post(
        "/api/change-requests",
        headers={"Authorization": f"Bearer {member_token}"},
        json={"section_id": sec.id, "title": "x", "skip_github": True},
    )
    cr_id = res.json()["id"]

    # member 가 status 변경 → 403
    res = await client.patch(
        f"/api/change-requests/{cr_id}",
        headers={"Authorization": f"Bearer {member_token}"},
        json={"status": "rejected"},
    )
    assert res.status_code == 403

    # admin 이 status 변경 → 200
    res = await client.patch(
        f"/api/change-requests/{cr_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"status": "rejected"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "rejected"
    assert res.json()["closed_at"] is not None


@pytest.mark.asyncio
async def test_patch_title_by_requester(client: AsyncClient, db_session: AsyncSession):
    sec = await _seed(db_session)
    token = await _login(client, "user@example.com")

    res = await client.post(
        "/api/change-requests",
        headers={"Authorization": f"Bearer {token}"},
        json={"section_id": sec.id, "title": "old", "skip_github": True},
    )
    cr_id = res.json()["id"]

    res = await client.patch(
        f"/api/change-requests/{cr_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "new", "priority": "urgent"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["title"] == "new"
    assert body["priority"] == "urgent"


# ---------------------------------------------------------------------------
# webhook endpoint (HMAC + JSON body)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_webhook_endpoint_valid_signature(client: AsyncClient, db_session: AsyncSession):
    """webhook endpoint 통과 — 실제 매칭 안 돼도 200 반환."""
    sec = await _seed(db_session)

    payload = {
        "action": "closed",
        "issue": {"number": 99999},
        "repository": {"full_name": "bluevlad/AllergyInsight"},
    }
    body = json.dumps(payload).encode()

    secret = "supersecret"
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    with patch("app.api.github_webhook.settings.github_webhook_secret", secret):
        res = await client.post(
            "/api/github/webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": "issues",
                "X-GitHub-Delivery": "test-1",
                "X-Hub-Signature-256": sig,
            },
        )
    assert res.status_code == 200
    assert res.json()["status"] in ("no_match", "ok")


@pytest.mark.asyncio
async def test_webhook_endpoint_invalid_signature_401(client: AsyncClient):
    body = b'{"foo":"bar"}'
    with patch("app.api.github_webhook.settings.github_webhook_secret", "secret"):
        res = await client.post(
            "/api/github/webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": "issues",
                "X-GitHub-Delivery": "test-bad",
                "X-Hub-Signature-256": "sha256=deadbeef",
            },
        )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_webhook_ping(client: AsyncClient):
    body = json.dumps({"zen": "Hello"}).encode()
    secret = "s"
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    with patch("app.api.github_webhook.settings.github_webhook_secret", secret):
        res = await client.post(
            "/api/github/webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": "ping",
                "X-GitHub-Delivery": "ping-1",
                "X-Hub-Signature-256": sig,
            },
        )
    assert res.status_code == 200
    assert res.json()["status"] == "pong"
