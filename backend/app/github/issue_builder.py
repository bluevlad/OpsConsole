"""변경요청 → GitHub Issue body (markdown) 빌더.

섹션 메타·자산·요청자 정보를 GitHub 측에서 즉시 컨텍스트로 활용 가능한 형태로 정리.
PR 작성자가 본문 첫 줄의 'Closes #123' 으로 자동 연결할 수 있도록 안내 포함.
"""
from __future__ import annotations

from app.models.change_request import OpsChangeRequest
from app.models.section import OpsSection, OpsSectionAsset
from app.models.service import OpsService
from app.models.user import OpsUser

PRIORITY_BADGES = {
    "low": "🟢 LOW",
    "normal": "⚪ NORMAL",
    "high": "🟠 HIGH",
    "urgent": "🔴 URGENT",
}


def build_issue_title(cr: OpsChangeRequest, section: OpsSection | None) -> str:
    """`[ops:section-code] 제목` 형식 — 일관된 검색·필터링."""
    prefix = f"[ops:{section.code}]" if section else "[ops]"
    return f"{prefix} {cr.title}"


def build_issue_body(
    cr: OpsChangeRequest,
    *,
    requester: OpsUser,
    service: OpsService | None,
    section: OpsSection | None,
    assets: list[OpsSectionAsset] | None = None,
    portal_base_url: str = "https://opsconsole.unmong.com",
) -> str:
    """Issue body 마크다운 생성."""
    badge = PRIORITY_BADGES.get(cr.priority, cr.priority)
    lines: list[str] = []

    lines.append(f"> {badge} · 발급: OpsConsole · 요청자: `{requester.email}`")
    lines.append("")

    if service:
        lines.append("### 서비스 / 섹션")
        lines.append("")
        lines.append(f"- **service**: `{service.code}` — {service.display_name}")
        if service.gateway_url:
            lines.append(f"- **gateway**: {service.gateway_url}")
        if service.repo_url:
            lines.append(f"- **repo**: {service.repo_url}")
    if section:
        lines.append(f"- **section**: `{section.code}` — {section.name}")
        lines.append(f"- **level**: {section.level} · **status**: {section.status}")
        if section.route:
            lines.append(f"- **route**: `{section.route}`")
        if section.owner_email:
            lines.append(f"- **owner**: {section.owner_email}")
        if section.backup_email:
            lines.append(f"- **backup**: {section.backup_email}")
    lines.append("")

    if assets:
        lines.append("### 관련 자산")
        lines.append("")
        groups: dict[str, list[str]] = {}
        for a in assets:
            groups.setdefault(a.asset_type, []).append(a.path)
        for atype in ("frontend", "backend_router", "service", "model", "table", "endpoint"):
            paths = groups.get(atype)
            if not paths:
                continue
            lines.append(f"- **{atype}**:")
            for p in paths:
                lines.append(f"  - `{p}`")
        lines.append("")

    lines.append("### 요청 내용")
    lines.append("")
    lines.append(cr.description_md or "_본문 없음_")
    lines.append("")

    if cr.attachments:
        lines.append("### 첨부")
        lines.append("")
        for a in cr.attachments:
            name = a.get("filename") or a.get("name") or "file"
            url = a.get("url")
            size = a.get("size")
            line = f"- [{name}]({url})" if url else f"- {name}"
            if size:
                line += f" ({size} bytes)"
            lines.append(line)
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        f"> 본 Issue 는 OpsConsole 변경요청 #{cr.id} 에서 발급되었습니다.\n"
        f"> 추적: {portal_base_url}/change-requests/{cr.id}\n"
        "> PR 작성 시 본문에 `Closes #ISSUE_NUMBER` 를 포함하면 자동 연동됩니다."
    )
    return "\n".join(lines)


def build_labels(section: OpsSection | None, priority: str | None) -> list[str]:
    labels = ["from:ops-console"]
    if section:
        labels.append(f"section:{section.code}")
    if priority:
        labels.append(f"priority:{priority}")
    return labels
