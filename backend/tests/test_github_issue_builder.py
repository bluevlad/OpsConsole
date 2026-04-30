"""issue_builder 단위 테스트."""
from __future__ import annotations

from datetime import datetime, timezone

from app.github.issue_builder import build_issue_body, build_issue_title, build_labels
from app.models.change_request import OpsChangeRequest
from app.models.section import OpsSection, OpsSectionAsset
from app.models.service import OpsService
from app.models.user import OpsUser


def _make_objects():
    cr = OpsChangeRequest(
        id=42,
        section_id=7,
        requester_id=1,
        title="배너 문구 수정",
        description_md="`AI 상담` 페이지 상단 배너의 어투를 친근하게 변경해주세요.",
        priority="high",
        status="submitted",
        attachments=[{"filename": "screenshot.png", "url": "https://x/y.png", "size": 12345}],
        created_at=datetime(2026, 4, 30, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 30, tzinfo=timezone.utc),
    )
    user = OpsUser(id=1, email="user@example.com", name="User", role="ops_member")
    svc = OpsService(
        id=10,
        code="allergyinsight",
        display_name="AllergyInsight",
        gateway_url="https://allergy.unmong.com",
        repo_url="https://github.com/bluevlad/AllergyInsight",
    )
    sec = OpsSection(
        id=7,
        service_id=10,
        code="ai-consult",
        name="AI 상담",
        level="public",
        status="live",
        route="/ai/consult",
        owner_email="rainend00@gmail.com",
    )
    assets = [
        OpsSectionAsset(section_id=7, asset_type="frontend", path="frontend/src/X.jsx"),
        OpsSectionAsset(section_id=7, asset_type="endpoint", path="POST /api/ai/consult"),
    ]
    return cr, user, svc, sec, assets


def test_build_issue_title():
    cr, _, _, sec, _ = _make_objects()
    assert build_issue_title(cr, sec) == "[ops:ai-consult] 배너 문구 수정"
    assert build_issue_title(cr, None) == "[ops] 배너 문구 수정"


def test_build_issue_body_has_section_and_assets():
    cr, user, svc, sec, assets = _make_objects()
    body = build_issue_body(cr, requester=user, service=svc, section=sec, assets=assets)

    assert "🟠 HIGH" in body
    assert "user@example.com" in body
    assert "allergyinsight" in body
    assert "https://allergy.unmong.com" in body
    assert "ai-consult" in body
    assert "frontend/src/X.jsx" in body
    assert "POST /api/ai/consult" in body
    assert "screenshot.png" in body
    assert "OpsConsole 변경요청 #42" in body
    assert "Closes #ISSUE_NUMBER" in body


def test_build_issue_body_handles_missing_section():
    cr, user, svc, _, _ = _make_objects()
    body = build_issue_body(cr, requester=user, service=svc, section=None, assets=None)
    assert "user@example.com" in body
    assert "ai-consult" not in body  # 섹션 없으면 노출되지 않음


def test_build_labels():
    cr, _, _, sec, _ = _make_objects()
    labels = build_labels(sec, cr.priority)
    assert "from:ops-console" in labels
    assert "section:ai-consult" in labels
    assert "priority:high" in labels


def test_build_labels_no_section():
    labels = build_labels(None, "low")
    assert labels == ["from:ops-console", "priority:low"]
