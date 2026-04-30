"""GitHub webhook handler — HMAC 검증 + 이벤트 라우팅 + idempotency."""
from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.github import webhook_handler
from app.manifest.parser import parse_manifest
from app.manifest.sync import upsert_catalog
from app.models.change_request import OpsChangeRequest, OpsChangeRequestEvent
from app.models.section import OpsSection
from app.models.service import OpsService
from app.models.user import OpsUser

FIXTURE = Path(__file__).parent / "fixtures" / "allergyinsight-manifest.yml"


# ----------------------- helpers -----------------------------------------


def _sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


async def _seed_with_user(db: AsyncSession) -> tuple[OpsService, OpsSection, OpsUser]:
    text = FIXTURE.read_text(encoding="utf-8")
    await upsert_catalog(db, parse_manifest(text), ref="test")
    svc = (
        await db.execute(select(OpsService).where(OpsService.code == "allergyinsight"))
    ).scalar_one()
    sec = (
        await db.execute(
            select(OpsSection).where(
                OpsSection.service_id == svc.id, OpsSection.code == "ai-consult"
            )
        )
    ).scalar_one()
    user = OpsUser(email="user@example.com", name="User", role="ops_member")
    db.add(user)
    await db.flush()
    return svc, sec, user


async def _make_cr(
    db: AsyncSession, *, repo_full_name: str, issue_number: int, section_id: int, requester_id: int
) -> OpsChangeRequest:
    cr = OpsChangeRequest(
        section_id=section_id,
        requester_id=requester_id,
        title="t",
        priority="normal",
        status="submitted",
        github_issue_number=issue_number,
        github_issue_url=f"https://github.com/{repo_full_name}/issues/{issue_number}",
    )
    db.add(cr)
    await db.flush()
    return cr


# ----------------------- signature verification -------------------------


def test_verify_signature_valid():
    body = b'{"hello": "world"}'
    sig = _sign("topsecret", body)
    assert webhook_handler.verify_signature("topsecret", body, sig) is True


def test_verify_signature_invalid_secret():
    body = b'{"hello": "world"}'
    sig = _sign("topsecret", body)
    assert webhook_handler.verify_signature("WRONG", body, sig) is False


def test_verify_signature_missing_or_malformed():
    assert webhook_handler.verify_signature("s", b"x", None) is False
    assert webhook_handler.verify_signature("s", b"x", "md5=abc") is False
    assert webhook_handler.verify_signature("", b"x", "sha256=abc") is False


# ----------------------- closing keyword extraction ----------------------


def test_extract_closing_issues_various():
    body = "This PR closes #12 and Fixes #7. Resolves #99."
    assert sorted(webhook_handler.extract_closing_issue_numbers(body)) == [7, 12, 99]


def test_extract_closing_issues_empty():
    assert webhook_handler.extract_closing_issue_numbers(None) == []
    assert webhook_handler.extract_closing_issue_numbers("no link here") == []


# ----------------------- event handling ----------------------------------


@pytest.mark.asyncio
async def test_issues_closed_marks_request_closed(db_session: AsyncSession):
    _, sec, user = await _seed_with_user(db_session)
    cr = await _make_cr(
        db_session,
        repo_full_name="bluevlad/AllergyInsight",
        issue_number=101,
        section_id=sec.id,
        requester_id=user.id,
    )

    payload = {
        "action": "closed",
        "issue": {"number": 101},
        "repository": {"full_name": "bluevlad/AllergyInsight"},
    }
    res = await webhook_handler.handle_event(
        db_session, event_type="issues", delivery_id="dlv-1", payload=payload
    )
    assert res["status"] == "ok"
    assert res["event"] == "issue_closed"
    await db_session.refresh(cr)
    assert cr.status == "closed"
    assert cr.closed_at is not None


@pytest.mark.asyncio
async def test_pr_merged_with_closes_keyword_marks_merged(db_session: AsyncSession):
    _, sec, user = await _seed_with_user(db_session)
    cr = await _make_cr(
        db_session,
        repo_full_name="bluevlad/AllergyInsight",
        issue_number=42,
        section_id=sec.id,
        requester_id=user.id,
    )

    payload = {
        "action": "closed",
        "pull_request": {
            "number": 7,
            "html_url": "https://github.com/bluevlad/AllergyInsight/pull/7",
            "body": "Closes #42 — refactor banner",
            "merged": True,
        },
        "repository": {"full_name": "bluevlad/AllergyInsight"},
    }
    res = await webhook_handler.handle_event(
        db_session, event_type="pull_request", delivery_id="dlv-2", payload=payload
    )
    assert res["status"] == "ok"
    assert res["event"] == "pr_merged"
    assert res["affected"] == [cr.id]
    await db_session.refresh(cr)
    assert cr.status == "merged"
    assert cr.github_pr_number == 7
    assert cr.github_pr_url == "https://github.com/bluevlad/AllergyInsight/pull/7"
    assert cr.closed_at is not None


@pytest.mark.asyncio
async def test_pr_opened_marks_in_pr(db_session: AsyncSession):
    _, sec, user = await _seed_with_user(db_session)
    cr = await _make_cr(
        db_session,
        repo_full_name="bluevlad/AllergyInsight",
        issue_number=11,
        section_id=sec.id,
        requester_id=user.id,
    )

    payload = {
        "action": "opened",
        "pull_request": {
            "number": 33,
            "html_url": "https://github.com/bluevlad/AllergyInsight/pull/33",
            "body": "Fixes #11",
            "merged": False,
        },
        "repository": {"full_name": "bluevlad/AllergyInsight"},
    }
    await webhook_handler.handle_event(
        db_session, event_type="pull_request", delivery_id="dlv-3", payload=payload
    )
    await db_session.refresh(cr)
    assert cr.status == "in_pr"
    assert cr.github_pr_number == 33


@pytest.mark.asyncio
async def test_pr_closed_unmerged_reverts_to_submitted(db_session: AsyncSession):
    _, sec, user = await _seed_with_user(db_session)
    cr = await _make_cr(
        db_session,
        repo_full_name="bluevlad/AllergyInsight",
        issue_number=12,
        section_id=sec.id,
        requester_id=user.id,
    )
    cr.status = "in_pr"
    await db_session.flush()

    payload = {
        "action": "closed",
        "pull_request": {
            "number": 50,
            "html_url": "https://github.com/bluevlad/AllergyInsight/pull/50",
            "body": "Closes #12",
            "merged": False,
        },
        "repository": {"full_name": "bluevlad/AllergyInsight"},
    }
    res = await webhook_handler.handle_event(
        db_session, event_type="pull_request", delivery_id="dlv-4", payload=payload
    )
    assert res["event"] == "pr_closed_unmerged"
    await db_session.refresh(cr)
    assert cr.status == "submitted"


@pytest.mark.asyncio
async def test_idempotency_on_same_delivery_id(db_session: AsyncSession):
    _, sec, user = await _seed_with_user(db_session)
    cr = await _make_cr(
        db_session,
        repo_full_name="bluevlad/AllergyInsight",
        issue_number=200,
        section_id=sec.id,
        requester_id=user.id,
    )

    payload = {
        "action": "closed",
        "issue": {"number": 200},
        "repository": {"full_name": "bluevlad/AllergyInsight"},
    }
    res1 = await webhook_handler.handle_event(
        db_session, event_type="issues", delivery_id="dlv-dup", payload=payload
    )
    assert res1["status"] == "ok"

    res2 = await webhook_handler.handle_event(
        db_session, event_type="issues", delivery_id="dlv-dup", payload=payload
    )
    assert res2["status"] == "duplicate"

    events = (
        await db_session.execute(
            select(OpsChangeRequestEvent).where(OpsChangeRequestEvent.request_id == cr.id)
        )
    ).scalars().all()
    # 'issue_closed' 1건 (중복 처리 안 됨)
    closed_events = [e for e in events if e.event_type == "issue_closed"]
    assert len(closed_events) == 1


@pytest.mark.asyncio
async def test_no_match_returns_no_match(db_session: AsyncSession):
    payload = {
        "action": "closed",
        "issue": {"number": 9999},
        "repository": {"full_name": "bluevlad/Unrelated"},
    }
    res = await webhook_handler.handle_event(
        db_session, event_type="issues", delivery_id="dlv-x", payload=payload
    )
    assert res["status"] == "no_match"
