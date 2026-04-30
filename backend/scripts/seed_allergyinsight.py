"""AllergyInsight 11섹션 시드 적재 CLI.

사용:
    python -m scripts.seed_allergyinsight

기본 동작: backend/tests/fixtures/allergyinsight-manifest.yml 을 sync.

옵션:
    --manifest PATH     다른 매니페스트 파일 경로 사용
    --ref REF           snapshot에 기록할 git ref (기본 'seed')
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.manifest.parser import parse_manifest
from app.manifest.sync import upsert_catalog

DEFAULT_MANIFEST = Path(__file__).parent.parent / "tests" / "fixtures" / "allergyinsight-manifest.yml"


async def main() -> int:
    ap = argparse.ArgumentParser(description="AllergyInsight 매니페스트 시드 적재")
    ap.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    ap.add_argument("--ref", type=str, default="seed")
    args = ap.parse_args()

    if not args.manifest.is_file():
        print(f"[error] manifest not found: {args.manifest}", file=sys.stderr)
        return 2

    text = args.manifest.read_text(encoding="utf-8")
    manifest = parse_manifest(text)
    print(f"[seed] service={manifest.service} sections={len(manifest.sections)}")

    engine = create_async_engine(settings.database_url)
    Session = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with Session() as session:
        report = await upsert_catalog(session, manifest, ref=args.ref)
        await session.commit()

    await engine.dispose()

    print(f"[seed] created={report.created}")
    print(f"[seed] added=  {report.sections_added}")
    print(f"[seed] updated={report.sections_updated}")
    print(f"[seed] deleted={report.sections_deleted}")
    print(f"[seed] snapshot_id={report.snapshot_id}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
