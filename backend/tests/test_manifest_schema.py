"""Pydantic 매니페스트 스키마 검증 테스트."""
from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.manifest.parser import ManifestParseError, parse_manifest
from app.manifest.schema import Manifest, Section

FIXTURE_DIR = Path(__file__).parent / "fixtures"
ALLERGY_MANIFEST = FIXTURE_DIR / "allergyinsight-manifest.yml"


# -- positive ---------------------------------------------------------------


def test_parse_allergyinsight_seed_manifest():
    """1호 고객 시드 — 11개 섹션 모두 검증 통과."""
    text = ALLERGY_MANIFEST.read_text(encoding="utf-8")
    manifest = parse_manifest(text)

    assert manifest.version == "1.0"
    assert manifest.service == "allergyinsight"
    assert manifest.display_name == "AllergyInsight"
    assert str(manifest.gateway_url).rstrip("/") == "https://allergy.unmong.com"

    assert len(manifest.sections) == 11
    codes = [s.code for s in manifest.sections]
    assert "ai-consult" in codes
    assert "drug-management" in codes  # Phase 1 beta

    levels = {s.level for s in manifest.sections}
    assert levels == {"public", "member", "admin"}


def test_section_assets_default_empty():
    """assets 미지정 시 빈 리스트 6개 — 매니페스트가 모든 자산 키를 명시할 필요 없음."""
    section = Section(code="x", name="X", level="public")
    assert section.assets.frontend == []
    assert section.assets.tables == []


def test_section_status_default_live():
    section = Section(code="x", name="X", level="public")
    assert section.status == "live"


# -- negative: 스키마 위반 ---------------------------------------------------


def test_reject_missing_required_field():
    """version 누락."""
    text = """
service: x
display_name: X
sections:
  - code: a
    name: A
    level: public
"""
    with pytest.raises(ManifestParseError, match="version"):
        parse_manifest(text)


def test_reject_invalid_level():
    text = """
version: "1.0"
service: x
display_name: X
sections:
  - code: a
    name: A
    level: superuser
"""
    with pytest.raises(ManifestParseError):
        parse_manifest(text)


def test_reject_invalid_service_code():
    """대문자/언더스코어 거부."""
    with pytest.raises(ValidationError):
        Manifest.model_validate(
            {
                "version": "1.0",
                "service": "Allergy_Insight",
                "display_name": "X",
                "sections": [{"code": "a", "name": "A", "level": "public"}],
            }
        )


def test_reject_unknown_field_in_section():
    """오타 필드 조기 발견 (additionalProperties: false 동등)."""
    with pytest.raises(ValidationError):
        Section.model_validate(
            {
                "code": "a",
                "name": "A",
                "level": "public",
                "owners": "x@y.z",  # 오타: owner 가 정답
            }
        )


def test_reject_duplicate_section_codes():
    text = """
version: "1.0"
service: x
display_name: X
sections:
  - code: a
    name: A
    level: public
  - code: a
    name: A2
    level: member
"""
    with pytest.raises(ManifestParseError, match="중복"):
        parse_manifest(text)


def test_reject_invalid_content_block_key():
    """key는 {section}.{block} 형태 (a.b) 만 허용."""
    text = """
version: "1.0"
service: x
display_name: X
sections:
  - code: a
    name: A
    level: public
    content_blocks:
      - key: invalidKey
"""
    with pytest.raises(ManifestParseError):
        parse_manifest(text)


def test_reject_empty_yaml():
    with pytest.raises(ManifestParseError, match="비어"):
        parse_manifest("")


def test_reject_yaml_root_list():
    with pytest.raises(ManifestParseError, match="매핑"):
        parse_manifest("- a\n- b\n")


def test_reject_invalid_yaml_syntax():
    with pytest.raises(ManifestParseError, match="yaml"):
        parse_manifest("version: 1.0\n  bad: indent: here")
