"""ops/manifest.yml 텍스트를 GitHub raw 또는 로컬 파일에서 가져온다.

우선순위:
1. settings.manifest_local_fallback_path (개발용 — GitHub PAT 미보유 시)
2. GitHub raw (요구: settings.github_pat)

repo_url은 매니페스트 루트의 `repo_url` 또는 ops_services.repo_url 사용.
"""
from __future__ import annotations

import re
from pathlib import Path

import httpx

from app.core.config import settings


class ManifestFetchError(RuntimeError):
    """매니페스트 fetch 실패."""


def _parse_github_repo(repo_url: str) -> tuple[str, str]:
    """https://github.com/{owner}/{repo}(.git)? → (owner, repo)."""
    m = re.match(r"^https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$", repo_url.strip())
    if not m:
        raise ManifestFetchError(f"GitHub URL 형식이 아님: {repo_url}")
    return m.group(1), m.group(2)


async def fetch_from_github(
    repo_url: str,
    *,
    path: str = "ops/manifest.yml",
    ref: str | None = None,
    timeout_s: float = 10.0,
) -> str:
    """GitHub raw에서 매니페스트 텍스트를 가져온다.

    Args:
        repo_url: https://github.com/{owner}/{repo}(.git)? 형식.
        path: repo 내 파일 경로 (기본 ops/manifest.yml).
        ref: branch / tag / SHA. None 이면 settings.manifest_default_ref.
        timeout_s: HTTP 타임아웃 초.

    Raises:
        ManifestFetchError: PAT 미설정, 4xx/5xx, 네트워크 오류.
    """
    if not settings.github_pat:
        raise ManifestFetchError(
            "GITHUB_PAT 미설정. .env에 PAT 추가하거나 fetch_local_fallback() 사용."
        )

    owner, repo = _parse_github_repo(repo_url)
    use_ref = ref or settings.manifest_default_ref
    api_url = (
        f"{settings.github_api_base}/repos/{owner}/{repo}/contents/{path}"
        f"?ref={use_ref}"
    )
    headers = {
        "Authorization": f"Bearer {settings.github_pat}",
        # raw 미디어 타입을 명시 — base64 디코딩 불필요
        "Accept": "application/vnd.github.raw",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "OpsConsole/0.0.1",
    }

    async with httpx.AsyncClient(timeout=timeout_s) as client:
        try:
            res = await client.get(api_url, headers=headers)
        except httpx.RequestError as e:
            raise ManifestFetchError(f"GitHub 요청 실패: {e}") from e

    if res.status_code == 404:
        raise ManifestFetchError(
            f"매니페스트 미존재: {owner}/{repo}@{use_ref}:{path}"
        )
    if res.status_code != 200:
        raise ManifestFetchError(
            f"GitHub {res.status_code}: {res.text[:200]}"
        )
    return res.text


def fetch_local_fallback(repo_root: str | Path, path: str = "ops/manifest.yml") -> str:
    """로컬 파일시스템에서 매니페스트를 읽는다 (개발용)."""
    file_path = Path(repo_root) / path
    if not file_path.is_file():
        raise ManifestFetchError(f"로컬 매니페스트 파일이 없음: {file_path}")
    return file_path.read_text(encoding="utf-8")
