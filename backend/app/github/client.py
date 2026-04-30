"""GitHub REST API 클라이언트 (httpx 기반).

P0 §2 fetcher 와 같은 토큰을 재사용. 본 모듈은 변경요청을 Issue 로 발급하는 용도.

Note: PyGithub 대신 httpx 직접 호출 — 의존성 최소화 + async 통일.
"""
from __future__ import annotations

import re

import httpx

from app.core.config import settings


class GitHubError(RuntimeError):
    """GitHub API 호출 실패 (auth/4xx/5xx)."""


def parse_owner_repo(repo_url: str) -> tuple[str, str]:
    """https://github.com/{owner}/{repo}(.git)? → (owner, repo)."""
    m = re.match(r"^https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$", repo_url.strip())
    if not m:
        raise GitHubError(f"GitHub URL 형식이 아님: {repo_url}")
    return m.group(1), m.group(2)


def _ensure_pat() -> str:
    if not settings.github_pat:
        raise GitHubError("GITHUB_PAT 미설정 — Issue 발급/조회 불가")
    return settings.github_pat


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_ensure_pat()}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "OpsConsole/0.1 (+https://opsconsole.unmong.com)",
    }


async def create_issue(
    repo_url: str,
    *,
    title: str,
    body: str,
    labels: list[str] | None = None,
    timeout_s: float = 10.0,
) -> dict:
    """Issue 생성. 응답 dict 반환 (number, html_url, ...).

    Raises:
        GitHubError: 401/403/404/422/5xx 등 비-201 응답.
    """
    owner, repo = parse_owner_repo(repo_url)
    url = f"{settings.github_api_base}/repos/{owner}/{repo}/issues"
    payload: dict = {"title": title, "body": body}
    if labels:
        payload["labels"] = labels

    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            res = await client.post(url, headers=_headers(), json=payload)
    except httpx.RequestError as e:
        raise GitHubError(f"GitHub 요청 실패: {e}") from e

    if res.status_code != 201:
        raise GitHubError(f"Issue 생성 실패 {res.status_code}: {res.text[:200]}")
    return res.json()


async def get_issue(repo_url: str, issue_number: int, *, timeout_s: float = 10.0) -> dict:
    owner, repo = parse_owner_repo(repo_url)
    url = f"{settings.github_api_base}/repos/{owner}/{repo}/issues/{issue_number}"
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        res = await client.get(url, headers=_headers())
    if res.status_code != 200:
        raise GitHubError(f"Issue 조회 실패 {res.status_code}: {res.text[:200]}")
    return res.json()


async def get_pull(repo_url: str, pr_number: int, *, timeout_s: float = 10.0) -> dict:
    owner, repo = parse_owner_repo(repo_url)
    url = f"{settings.github_api_base}/repos/{owner}/{repo}/pulls/{pr_number}"
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        res = await client.get(url, headers=_headers())
    if res.status_code != 200:
        raise GitHubError(f"PR 조회 실패 {res.status_code}: {res.text[:200]}")
    return res.json()
