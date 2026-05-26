import asyncio
from src.workers.task_watchdog import task_watchdog
from src.workers.daily_briefing import daily_briefing_pipeline
from src.workers.agent_worker import agent_worker


class WorkerScheduler:
    def __init__(self):
        self._workers: list[tuple[str, any]] = []
        self._running = False

    def register(self, name: str, worker, interval_seconds: int):
        self._workers.append((name, worker, interval_seconds))

    async def start_all(self):
        self._running = True
        await agent_worker.start()
        print("[Scheduler] AgentWorker 已启动 (5s间隔)")
        await task_watchdog.start()
        print("[Scheduler] TaskWatchdog 已启动 (60s间隔)")
        print("[Scheduler] DailyBriefing 已注册 (按需触发)")

    async def stop_all(self):
        self._running = False
        await agent_worker.stop()
        await task_watchdog.stop()
        print("[Scheduler] 所有Worker已停止")

    async def run_once(self, worker_name: str):
        if worker_name == "watchdog":
            await task_watchdog.check_all_tasks()
        elif worker_name == "briefing":
            await daily_briefing_pipeline.run_once()
        elif worker_name == "agent":
            async with __import__("src.core.database", fromlist=["async_session_factory"]).async_session_factory() as session:
                pass  # agent worker polls on its own


scheduler = WorkerScheduler()
