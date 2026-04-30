"""manifest fetcher — GitHub raw + local fallback 단위 테스트."""
from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from app.manifest import fetcher


@pytest.fixture
def patch_github_pat(monkeypatch: pytest.MonkeyPatch):
    """settings.github_pat 임시 주입 — 재사용 fixture."""
    monkeypatch.setattr(fetcher.settings, "github_pat", "ghp_test_token", raising=True)


# -- _parse_github_repo -----------------------------------------------------


@pytest.mark.parametrize(
    "url, owner, repo",
    [
        ("https://github.com/bluevlad/AllergyInsight", "bluevlad", "AllergyInsight"),
        ("https://github.com/bluevlad/AllergyInsight.git", "bluevlad", "AllergyInsight"),
        ("https://github.com/bluevlad/AllergyInsight/", "bluevlad", "AllergyInsight"),
    ],
)
def test_parse_github_repo_variants(url, owner, repo):
    assert fetcher._parse_github_repo(url) == (owner, repo)


def test_parse_github_repo_rejects_non_github():
    with pytest.raises(fetcher.ManifestFetchError):
        fetcher._parse_github_repo("https://gitlab.com/x/y")


# -- fetch_from_github (HTTP) -----------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_fetch_from_github_success(patch_github_pat):
    body = "version: '1.0'\nservice: x\ndisplay_name: X\nsections: [{code: a, name: A, level: public}]\n"
    route = respx.get(
        "https://api.github.com/repos/bluevlad/AllergyInsight/contents/ops/manifest.yml?ref=main"
    ).mock(return_value=httpx.Response(200, text=body))

    text = await fetcher.fetch_from_github("https://github.com/bluevlad/AllergyInsight")

    assert text == body
    req = route.calls[0].request
    assert req.headers["authorization"] == "Bearer ghp_test_token"
    assert "vnd.github.raw" in req.headers["accept"]


@pytest.mark.asyncio
@respx.mock
async def test_fetch_from_github_404_raises(patch_github_pat):
    respx.get(
        "https://api.github.com/repos/bluevlad/AllergyInsight/contents/ops/manifest.yml?ref=main"
    ).mock(return_value=httpx.Response(404, text="Not Found"))

    with pytest.raises(fetcher.ManifestFetchError, match="미존재"):
        await fetcher.fetch_from_github("https://github.com/bluevlad/AllergyInsight")


@pytest.mark.asyncio
@respx.mock
async def test_fetch_from_github_500_raises(patch_github_pat):
    respx.get(
        "https://api.github.com/repos/bluevlad/AllergyInsight/contents/ops/manifest.yml?ref=main"
    ).mock(return_value=httpx.Response(500, text="boom"))

    with pytest.raises(fetcher.ManifestFetchError, match="500"):
        await fetcher.fetch_from_github("https://github.com/bluevlad/AllergyInsight")


@pytest.mark.asyncio
async def test_fetch_from_github_requires_pat(monkeypatch):
    monkeypatch.setattr(fetcher.settings, "github_pat", "", raising=True)
    with pytest.raises(fetcher.ManifestFetchError, match="GITHUB_PAT"):
        await fetcher.fetch_from_github("https://github.com/x/y")


@pytest.mark.asyncio
@respx.mock
async def test_fetch_from_github_uses_explicit_ref(patch_github_pat):
    respx.get(
        "https://api.github.com/repos/o/r/contents/ops/manifest.yml?ref=feature-x"
    ).mock(return_value=httpx.Response(200, text="ok"))

    out = await fetcher.fetch_from_github("https://github.com/o/r", ref="feature-x")
    assert out == "ok"


# -- fetch_local_fallback ---------------------------------------------------


def test_fetch_local_fallback_reads_file(tmp_path: Path):
    repo = tmp_path / "repo"
    (repo / "ops").mkdir(parents=True)
    (repo / "ops" / "manifest.yml").write_text("version: '1.0'\n", encoding="utf-8")

    text = fetcher.fetch_local_fallback(repo)
    assert "version" in text


def test_fetch_local_fallback_missing_raises(tmp_path: Path):
    with pytest.raises(fetcher.ManifestFetchError, match="없음"):
        fetcher.fetch_local_fallback(tmp_path)
