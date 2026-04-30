"""pytest 공용 fixtures — DB 세션 격리(rollback) 등."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings


async def _truncate_all() -> None:
    """opsconsole_dev의 OpsConsole 테이블 전체 비우기. CASCADE FK 활용."""
    engine = create_async_engine(settings.database_url, echo=False)
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM ops_audit_log"))
        await conn.execute(text("DELETE FROM ops_manifest_snapshots"))
        await conn.execute(text("DELETE FROM ops_services"))  # CASCADE → sections, assets
        await conn.execute(text("DELETE FROM ops_users"))
    await engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def _clean_db_session_start():
    """세션 시작 시 1회 — 시드 CLI 등으로 영구 적재된 데이터 정리.

    rollback 격리(db_session)는 테스트가 자체 INSERT 한 데이터만 되돌릴 수 있다.
    이전에 commit 된 데이터(시드)는 별도로 정리해야 테스트가 깨끗한 상태에서 시작한다.
    """
    asyncio.run(_truncate_all())
    yield


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """매 테스트마다 트랜잭션을 시작하고 끝나면 rollback — DB 상태 격리."""
    engine = create_async_engine(settings.database_url, echo=False)
    async with engine.connect() as conn:
        trans = await conn.begin()
        SessionLocal = async_sessionmaker(bind=conn, expire_on_commit=False)
        async with SessionLocal() as session:
            try:
                yield session
            finally:
                await trans.rollback()
    await engine.dispose()
