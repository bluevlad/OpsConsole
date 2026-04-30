"""pytest 공용 fixtures — DB 세션 격리(rollback) 등."""
from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """매 테스트마다 트랜잭션을 시작하고 끝나면 rollback — DB 상태 격리.

    공유 PostgreSQL의 opsconsole_dev DB에 실제 INSERT/SELECT가 일어나지만
    rollback 으로 깨끗이 되돌린다.
    """
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
