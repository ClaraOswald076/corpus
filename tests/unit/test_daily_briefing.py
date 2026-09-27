"""每日简报幂等回归测试：同日重复 run_once 不再撞 UNIQUE 约束崩溃。

对应 issue #47：旧幂等守卫只认 status=="sent"，首次生成落库 status="draft"，
同日二次执行 INSERT 撞 briefing_date 唯一约束，CLI 无捕获直接全栈崩溃。

运行：python -m pytest tests/unit/test_daily_briefing.py -q
"""
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.models.daily_briefing import DailyBriefing
from src.workers import daily_briefing as briefing_module
from src.workers.daily_briefing import daily_briefing_pipeline


@pytest.fixture
def briefing_factory(db_engine, monkeypatch):
    # 把 pipeline 内部的 session 工厂指到测试引擎，不经调度器、不碰真实库
    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(briefing_module, "async_session_factory", factory)
    return factory


@pytest.mark.asyncio
async def test_second_run_same_day_returns_none(briefing_factory):
    # 首次生成落库 status="draft"，同日第二次必须返回 None 跳过，且只有一行
    first = await daily_briefing_pipeline.run_once()
    assert first is not None
    assert first.status == "draft"
    assert first.briefing_date == date.today()

    second = await daily_briefing_pipeline.run_once()
    assert second is None

    async with briefing_factory() as s:
        rows = (await s.execute(select(DailyBriefing))).scalars().all()
        assert len(rows) == 1
        assert rows[0].briefing_date == date.today()


@pytest.mark.asyncio
async def test_sent_briefing_skipped_too(briefing_factory):
    # 已发送的简报同样跳过（run_once 对"今天已有"统一返回 None）
    await daily_briefing_pipeline.run_once()
    async with briefing_factory() as s:
        row = (await s.execute(select(DailyBriefing))).scalars().one()
        row.status = "sent"
        await s.commit()

    again = await daily_briefing_pipeline.run_once()
    assert again is None

    async with briefing_factory() as s:
        assert len((await s.execute(select(DailyBriefing))).scalars().all()) == 1


@pytest.mark.asyncio
async def test_failed_briefing_regenerates_single_row(briefing_factory):
    # failed 保留重试语义：重跑重新生成，复用唯一行、不产生第二行
    await daily_briefing_pipeline.run_once()
    async with briefing_factory() as s:
        row = (await s.execute(select(DailyBriefing))).scalars().one()
        row.content = "# 旧内容（生成失败）"
        row.status = "failed"
        await s.commit()

    retried = await daily_briefing_pipeline.run_once()
    assert retried is not None
    assert retried.status == "draft"
    assert retried.content != "# 旧内容（生成失败）"

    async with briefing_factory() as s:
        rows = (await s.execute(select(DailyBriefing))).scalars().all()
        assert len(rows) == 1
        assert rows[0].status == "draft"
