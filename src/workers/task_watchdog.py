import asyncio
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import async_session_factory
from src.core.timeutils import as_aware_utc
from src.repositories.task_repo import TaskRepository
from src.services.escalation_engine import EscalationEngine, EscalationReason
from src.services.task_manager import TaskStatus


class TaskWatchdog:
    def __init__(self, check_interval_seconds: int = 60):
        self.check_interval = check_interval_seconds
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self):
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()

    async def _loop(self):
        while self._running:
            try:
                await self.check_all_tasks()
            except Exception as e:
                print(f"[Watchdog] 检查出错: {e}")
            await asyncio.sleep(self.check_interval)

    async def check_all_tasks(self):
        async with async_session_factory() as session:
            repo = TaskRepository(session)
            engine = EscalationEngine(session)

            # Check for timed-out tasks
            in_progress_tasks = await repo.list_all(status=TaskStatus.IN_PROGRESS.value, limit=500)
            now = datetime.now(timezone.utc)
            for task in in_progress_tasks:
                if task.timeout_seconds and task.started_at:
                    elapsed = (now - as_aware_utc(task.started_at)).total_seconds()
                    if elapsed > task.timeout_seconds:
                        task.status = TaskStatus.FAILED.value
                        await repo.update(task)
                        try:
                            await engine.escalate(task.id, EscalationReason.TIMEOUT)
                        except Exception:
                            pass

            # Check for blocked tasks that might need escalation
            blocked_tasks = await repo.list_all(status=TaskStatus.BLOCKED.value, limit=200)
            for task in blocked_tasks:
                deps_satisfied = await repo.are_all_dependencies_satisfied(task.id)
                if not deps_satisfied and task.started_at:
                    blocked_hours = (now - as_aware_utc(task.started_at)).total_seconds() / 3600
                    if blocked_hours > 24:  # Blocked for more than a day
                        try:
                            await engine.escalate(task.id, EscalationReason.BLOCKED_DEPENDENCY)
                        except Exception:
                            pass

            # Check for failed tasks needing escalation
            failed_tasks = await repo.list_all(status=TaskStatus.FAILED.value, limit=200)
            for task in failed_tasks:
                if task.retry_count >= task.max_retries:
                    try:
                        await engine.escalate(task.id, EscalationReason.MAX_RETRIES_EXCEEDED)
                    except Exception:
                        pass

            needs_clarification = await repo.list_all(status=TaskStatus.NEEDS_CLARIFICATION.value, limit=100)
            for task in needs_clarification:
                try:
                    await engine.escalate(task.id, EscalationReason.NEEDS_CLARIFICATION)
                except Exception:
                    pass

            await session.commit()

    async def check_single_task(self, task_id):
        async with async_session_factory() as session:
            repo = TaskRepository(session)
            engine = EscalationEngine(session)
            task = await repo.get(task_id)
            if not task:
                return None

            analysis = await engine.analyze_failure(task_id)
            if analysis:
                event = await engine.escalate(task_id, analysis.reason)
                await session.commit()
                return {"analysis": analysis, "escalation_event": event}
            return None


task_watchdog = TaskWatchdog()
