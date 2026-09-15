from unittest.mock import AsyncMock, patch

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.cli.seed import seed_default_org
from src.models.base import Base
from src.models.organization import Department


async def test_seed_default_org_is_idempotent(capsys):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    with patch("src.cli.seed.init_db", new=AsyncMock()), \
         patch("src.cli.seed.async_session_factory", factory):
        await seed_default_org()
        await seed_default_org()

    async with factory() as session:
        count = await session.scalar(select(func.count()).select_from(Department))
    assert count == 11
    assert "跳过初始化" in capsys.readouterr().out

    await engine.dispose()
