"""Regression tests for the watchdog pass on SQLite (naive datetime reads)."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession
from sqlalchemy.pool import StaticPool

from src.models.base import Base
from src.models.organization import Department, Agent
from src.models.task import Task
from src.workers import task_watchdog
from src.services.task_manager import TaskManagerService, TaskCreate, TaskStatus
from src.services.escalation_engine import EscalationEngine


@pytest.mark.asyncio
async def test_watchdog_timeout_escalates(monkeypatch):
    """check_all_tasks opens its own session, so task timestamps arrive naive
    from SQLite; the pass must still detect the timeout and escalate."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(task_watchdog, "async_session_factory", factory)

    async with factory() as session:
        dept = Department(name="wd部门", org_path="/wd", tier=1, dept_type="department")
        session.add(dept)
        await session.flush()
        head = Agent(name="负责人", role="部门负责人", department_id=dept.id,
                     agent_folder_path="agents/wd/head")
        session.add(head)
        await session.flush()
        worker = Agent(name="执行者", role="执行者", department_id=dept.id,
                       agent_folder_path="agents/wd/worker", reports_to_agent_id=head.id)
        session.add(worker)
        await session.commit()

        svc = TaskManagerService(session)
        task = await svc.create_task(TaskCreate(
            title="超时任务", created_by="test", assigned_agent_id=worker.id))
        await svc.mark_in_progress(task.id)
        task.timeout_seconds = 60
        task.started_at = datetime.now(timezone.utc) - timedelta(hours=2)
        await session.commit()
        task_id = task.id

    # Runs in a separate session: started_at comes back naive from SQLite.
    await task_watchdog.task_watchdog.check_all_tasks()

    async with factory() as session:
        row = await session.get(Task, task_id)
        events = await EscalationEngine(session).get_escalations(task_id=task_id)
        assert row.status == TaskStatus.FAILED.value
        assert len(events) == 1
        assert events[0].reason == "timeout"

    await engine.dispose()
