import asyncio
from datetime import datetime, timezone, date
from src.core.database import async_session_factory
from src.repositories.meeting_repo import MeetingRepository
from src.repositories.task_repo import TaskRepository
from src.repositories.agent_repo import AgentRepository
from src.repositories.organization_repo import DepartmentRepository
from src.models.daily_briefing import DailyBriefing


class DailyBriefingPipeline:
    def __init__(self):
        self._running = False
        self._task: asyncio.Task | None = None

    async def run_once(self, secretariat_agent_id=None, communications_agent_id=None):
        """Run the full daily briefing pipeline once"""
        async with async_session_factory() as session:
            today = date.today()

            # Check if already generated
            from sqlalchemy import select
            result = await session.execute(
                select(DailyBriefing).where(DailyBriefing.briefing_date == today)
            )
            existing = result.scalar_one_or_none()
            if existing and existing.status == "sent":
                return existing

            meeting_repo = MeetingRepository(session)
            task_repo = TaskRepository(session)
            agent_repo = AgentRepository(session)
            dept_repo = DepartmentRepository(session)

            # Gather data
            meetings = await meeting_repo.list_all(limit=50)
            today_meetings = [
                m for m in meetings
                if m.started_at and m.started_at.date() == today
            ]

            tasks = await task_repo.list_all(limit=200)
            active_tasks = [t for t in tasks if t.status in ("pending", "in_progress", "blocked")]
            completed_today = [
                t for t in tasks
                if t.completed_at and t.completed_at.date() == today and t.status == "completed"
            ]
            failed_tasks = [t for t in tasks if t.status in ("failed", "needs_clarification")]

            agents = await agent_repo.list_all()
            active_agents = [a for a in agents if a.is_active]

            # Build briefing content
            sections = []
            sections.append(f"# 每日简报 - {today.isoformat()}")
            sections.append(f"\n## 概览")
            sections.append(f"- 活跃Agent: {len(active_agents)}")
            sections.append(f"- 进行中任务: {len(active_tasks)}")
            sections.append(f"- 今日完成: {len(completed_today)}")
            sections.append(f"- 今日会议: {len(today_meetings)}")

            if today_meetings:
                sections.append(f"\n## 今日会议 ({len(today_meetings)})")
                for m in today_meetings:
                    sections.append(f"- [{m.meeting_code}] {m.title} ({m.meeting_type}) — {m.status}")

            if active_tasks:
                sections.append(f"\n## 进行中任务 ({len(active_tasks)})")
                for t in active_tasks[:10]:
                    sections.append(f"- [{t.task_code}] {t.title} — {t.status} ({t.priority})")

            if completed_today:
                sections.append(f"\n## 今日完成 ({len(completed_today)})")
                for t in completed_today[:10]:
                    sections.append(f"- [{t.task_code}] {t.title}")

            if failed_tasks:
                sections.append(f"\n## ⚠ 需要关注")
                for t in failed_tasks[:5]:
                    sections.append(f"- [{t.task_code}] {t.title} — {t.status} (重试{t.retry_count}/{t.max_retries})")

            content = "\n".join(sections)

            gen_by = secretariat_agent_id or (agents[0].id if agents else None)

            briefing = DailyBriefing(
                briefing_date=today,
                generated_by=gen_by,
                reviewed_by=communications_agent_id,
                content=content,
                status="draft",
            )
            session.add(briefing)
            await session.commit()
            return briefing

    async def start(self, interval_hours: int = 24):
        self._running = True
        self._task = asyncio.create_task(self._loop(interval_hours))

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()

    async def _loop(self, interval_hours: int):
        while self._running:
            try:
                await self.run_once()
            except Exception as e:
                print(f"[Briefing] 生成出错: {e}")
            await asyncio.sleep(interval_hours * 3600)


daily_briefing_pipeline = DailyBriefingPipeline()
