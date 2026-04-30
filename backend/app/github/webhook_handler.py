"""GitHub webhook 처리 — HMAC 검증 + 이벤트 라우팅 + idempotency.

지원 이벤트:
- issues.closed   → 변경요청 status='closed'
- pull_request.opened / closed (merged) → status='in_pr' / 'merged' (issue 본문에 'Closes #N')

idempotency: X-GitHub-Delivery 헤더를 ops_change_request_events.github_event_id 에 저장.
이미 같은 delivery_id 가 있으면 noop.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.audit import OpsAuditLog
from app.models.change_request import OpsChangeRequest, OpsChangeRequestEvent

log = logging.getLogger("opsconsole.github.webhook")

# "Closes #123", "closes #123", "fixes #45", "resolves #78" — GitHub 표준 키워드
_CLOSE_KEYWORDS_RE = re.compile(
    r"\b(?:closes|close|closed|fixes|fix|fixed|resolves|resolve|resolved)\s+#(\d+)\b",
    re.IGNORECASE,
)


def verify_signature(secret: str, body: bytes, signature_header: str | None) -> bool:
    """X-Hub-Signature-256: sha256={hex} 검증."""
    if not secret:
        return False
    if not signature_header:
        return False
    if not signature_header.startswith("sha256="):
        return False
    given = signature_header[len("sha256=") :]
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, given)


def extract_closing_issue_numbers(pr_body: str | None) -> list[int]:
    """PR body 의 'Closes #N' 형태 → issue 번호 목록."""
    if not pr_body:
        return []
    return [int(n) for n in _CLOSE_KEYWORDS_RE.findall(pr_body)]


async def _already_processed(db: AsyncSession, delivery_id: str) -> bool:
    if not delivery_id:
        return False
    existing = (
        await db.execute(
            select(OpsChangeRequestEvent.id).where(
                OpsChangeRequestEvent.github_event_id == delivery_id
            )
        )
    ).first()
    return existing is not None


async def _find_cr_by_issue(
    db: AsyncSession, repo_full_name: str, issue_number: int
) -> OpsChangeRequest | None:
    """issue_number + repo URL 로 변경요청 조회.

    repo_full_name = '{owner}/{repo}'.
    """
    expected_url = f"https://github.com/{repo_full_name}/issues/{issue_number}"
    return (
        await db.execute(
            select(OpsChangeRequest).where(
                OpsChangeRequest.github_issue_number == issue_number,
                OpsChangeRequest.github_issue_url == expected_url,
            )
        )
    ).scalar_one_or_none()


async def _find_crs_by_pr_links(
    db: AsyncSession, repo_full_name: str, issue_numbers: list[int]
) -> list[OpsChangeRequest]:
    if not issue_numbers:
        return []
    expected_urls = [
        f"https://github.com/{repo_full_name}/issues/{n}" for n in issue_numbers
    ]
    return (
        (
            await db.execute(
                select(OpsChangeRequest).where(
                    OpsChangeRequest.github_issue_number.in_(issue_numbers),
                    OpsChangeRequest.github_issue_url.in_(expected_urls),
                )
            )
        )
        .scalars()
        .all()
    )


async def handle_event(
    db: AsyncSession,
    *,
    event_type: str,
    delivery_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """webhook 이벤트 처리. 결과 dict (action, affected_count, ...)."""
    # idempotency
    if await _already_processed(db, delivery_id):
        return {"status": "duplicate", "delivery_id": delivery_id}

    repo_full_name = payload.get("repository", {}).get("full_name", "")
    if event_type == "issues":
        return await _handle_issues(db, payload, delivery_id, repo_full_name)
    if event_type == "pull_request":
        return await _handle_pr(db, payload, delivery_id, repo_full_name)
    if event_type == "ping":
        return {"status": "pong"}

    return {"status": "ignored", "event_type": event_type}


async def _handle_issues(
    db: AsyncSession, payload: dict, delivery_id: str, repo_full_name: str
) -> dict[str, Any]:
    action = payload.get("action")
    issue = payload.get("issue") or {}
    number = issue.get("number")
    if not number:
        return {"status": "ignored", "reason": "no issue.number"}

    cr = await _find_cr_by_issue(db, repo_full_name, int(number))
    if cr is None:
        return {"status": "no_match", "issue_number": number}

    if action == "closed":
        if cr.status not in ("merged", "closed", "rejected"):
            cr.status = "closed"
            cr.closed_at = datetime.now(timezone.utc)
        evt_type = "issue_closed"
    elif action == "reopened":
        if cr.status == "closed":
            cr.status = "submitted"
            cr.closed_at = None
        evt_type = "issue_reopened"
    elif action == "opened":
        evt_type = "issue_opened"
    else:
        evt_type = f"issue_{action}"

    db.add(
        OpsChangeRequestEvent(
            request_id=cr.id,
            event_type=evt_type,
            github_event_id=delivery_id,
            payload={"action": action, "number": number},
        )
    )
    db.add(
        OpsAuditLog(
            actor_id=None,
            action="github_webhook",
            target_type="ops_change_requests",
            target_id=str(cr.id),
            payload={"event": "issues", "action": action, "issue_number": number},
        )
    )
    await db.commit()
    return {"status": "ok", "event": evt_type, "request_id": cr.id}


async def _handle_pr(
    db: AsyncSession, payload: dict, delivery_id: str, repo_full_name: str
) -> dict[str, Any]:
    action = payload.get("action")
    pr = payload.get("pull_request") or {}
    pr_number = pr.get("number")
    pr_body = pr.get("body") or ""
    pr_html_url = pr.get("html_url")
    merged = bool(pr.get("merged"))

    issue_numbers = extract_closing_issue_numbers(pr_body)
    matched = await _find_crs_by_pr_links(db, repo_full_name, issue_numbers)

    if not matched:
        return {"status": "no_match", "pr_number": pr_number}

    if action == "opened" or action == "reopened":
        evt_type = "pr_opened"
        for cr in matched:
            if cr.status in ("submitted",):
                cr.status = "in_pr"
            cr.github_pr_number = pr_number
            cr.github_pr_url = pr_html_url
    elif action == "closed":
        if merged:
            evt_type = "pr_merged"
            for cr in matched:
                cr.status = "merged"
                cr.closed_at = datetime.now(timezone.utc)
                cr.github_pr_number = pr_number
                cr.github_pr_url = pr_html_url
        else:
            evt_type = "pr_closed_unmerged"
            for cr in matched:
                if cr.status == "in_pr":
                    cr.status = "submitted"
    else:
        evt_type = f"pr_{action}"

    for cr in matched:
        db.add(
            OpsChangeRequestEvent(
                request_id=cr.id,
                event_type=evt_type,
                github_event_id=delivery_id,
                payload={
                    "action": action,
                    "pr_number": pr_number,
                    "merged": merged,
                    "linked_issues": issue_numbers,
                },
            )
        )

    db.add(
        OpsAuditLog(
            actor_id=None,
            action="github_webhook",
            target_type="ops_change_requests",
            target_id=",".join(str(cr.id) for cr in matched),
            payload={
                "event": "pull_request",
                "action": action,
                "merged": merged,
                "pr_number": pr_number,
                "linked_issues": issue_numbers,
            },
        )
    )
    await db.commit()
    return {
        "status": "ok",
        "event": evt_type,
        "affected": [cr.id for cr in matched],
    }
