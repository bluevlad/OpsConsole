"""yaml 텍스트 → Manifest Pydantic 모델 변환."""
from __future__ import annotations

import yaml
from pydantic import ValidationError

from app.manifest.schema import Manifest


class ManifestParseError(ValueError):
    """yaml 파싱 실패 또는 스키마 검증 실패."""


def parse_manifest(text: str) -> Manifest:
    """
    yaml 텍스트를 검증된 Manifest 모델로 변환한다.

    Raises:
        ManifestParseError: yaml 파싱 실패 또는 스키마 위반 시.
    """
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise ManifestParseError(f"yaml 파싱 실패: {e}") from e

    if raw is None:
        raise ManifestParseError("매니페스트 파일이 비어있습니다")
    if not isinstance(raw, dict):
        raise ManifestParseError(
            f"매니페스트 루트는 매핑(dict)이어야 합니다. 실제: {type(raw).__name__}"
        )

    try:
        return Manifest.model_validate(raw)
    except ValidationError as e:
        raise ManifestParseError(f"매니페스트 스키마 위반:\n{e}") from e
