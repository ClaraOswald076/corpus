import asyncio
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from src.core.database import async_session_factory
from src.models.organization import Agent as AgentModel, Department
from src.models.agent import ModelPreset
from src.models.task import Task
from src.services.task_manager import TaskManagerService, TaskStatus
from src.utils.llm_client import ModelPresetData
from src.utils.security import decrypt_api_key
from src.agents.base_agent import BaseAgent
from src.core.config import settings


class AgentWorker:
    def __init__(self, poll_interval_seconds: int = 5):
        self.poll_interval = poll_interval_seconds
        self._running = False
        self._task: asyncio.Task | None = None
        self._processing: set = set()

    async def start(self):
        self._running = True
        self._task = asyncio.create_task(self._loop())
        print(f"[AgentWorker] 已启动 (间隔{self.poll_interval}s)")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()

    async def _loop(self):
        while self._running:
            try:
                await self._poll_and_execute()
            except Exception as e:
                print(f"[AgentWorker] 轮询异常: {e}")
            await asyncio.sleep(self.poll_interval)

    async def _poll_and_execute(self):
        async with async_session_factory() as session:
            # Find pending tasks assigned to agents
            result = await session.execute(
                select(Task)
                .where(
                    Task.status == TaskStatus.PENDING.value,
                    Task.assigned_agent_id.isnot(None),
                )
                .order_by(Task.priority == "critical",
                          Task.priority == "high",
                          Task.created_at)
                .limit(5)
            )
            pending_tasks = result.scalars().all()

            for task in pending_tasks:
                if task.id in self._processing:
                    continue
                self._processing.add(task.id)
                try:
                    await self._execute_task(session, task)
                except Exception as e:
                    print(f"[AgentWorker] 任务 {task.task_code} 执行失败: {e}")
                finally:
                    self._processing.discard(task.id)
                break  # Execute one task per poll cycle

    async def _execute_task(self, session, task: Task):
        # Load agent with eager relationships
        result = await session.execute(
            select(AgentModel)
            .options(
                selectinload(AgentModel.department),
                selectinload(AgentModel.model_preset).selectinload(ModelPreset.api_keys),
            )
            .where(AgentModel.id == task.assigned_agent_id)
        )
        agent = result.scalar_one_or_none()
        if not agent or not agent.is_active:
            return

        if not agent.model_preset or not agent.model_preset.is_active:
            return

        # Decrypt API key
        mp = agent.model_preset
        api_key = ""
        if mp.api_keys:
            active_keys = [k for k in mp.api_keys if k.is_active]
            if active_keys:
                try:
                    api_key = decrypt_api_key(active_keys[0].encrypted_key)
                except Exception:
                    pass

        model_preset = ModelPresetData(
            name=mp.name,
            litellm_model_string=mp.litellm_model_string,
            default_params=mp.default_params or {},
            api_key=api_key,
        )

        dept_name = agent.department.name if agent.department else "未知部门"
        dept_tier = agent.department.tier if agent.department else 2
        folder_path = str(settings.project_root / agent.agent_folder_path)

        bot = BaseAgent(
            agent_id=agent.id, name=agent.name, role=agent.role,
            department_name=dept_name, tier=dept_tier,
            folder_path=folder_path, model_preset=model_preset,
            system_prompt=agent.system_prompt or "",
            max_memory_tokens=agent.max_memory_tokens,
            temperature=agent.temperature, max_tokens=agent.max_tokens,
        )

        # Mark in progress
        task_svc = TaskManagerService(session)
        await task_svc.mark_in_progress(task.id, f"agent:{agent.id}")
        await session.commit()
        print(f"[AgentWorker] {agent.name} 开始执行 {task.task_code}: {task.title}")

        # Check if sub-tasks exist - if so, just mark completed (sub-tasks are the real work)
        from src.repositories.task_repo import TaskRepository
        task_repo = TaskRepository(session)
        sub_tasks = await task_repo.list_sub_tasks(task.id)

        if sub_tasks:
            # Parent task with sub-tasks: check if all sub-tasks are done
            all_done = all(st.status == TaskStatus.COMPLETED.value for st in sub_tasks)
            if all_done:
                await task_svc.mark_completed(task.id, "所有子任务已完成", f"agent:{agent.id}")
            else:
                # Keep in progress until sub-tasks are done
                pending_count = sum(1 for st in sub_tasks if st.status == TaskStatus.PENDING.value)
                in_progress_count = sum(1 for st in sub_tasks if st.status == TaskStatus.IN_PROGRESS.value)
                await session.commit()  # Just commit the in_progress status
        else:
            # Leaf task: execute it
            prompt = f"""请完成以下任务：

任务编号: {task.task_code}
任务标题: {task.title}
任务描述: {task.description or '无额外描述'}
优先级: {task.priority}
标签: {', '.join(task.tags) if task.tags else '无'}

请按照你的角色和职责，生成完整的执行结果。输出应结构化、可直接使用。"""

            result = await bot.think(prompt)

            if result.success:
                # Save artifact
                await task_repo.create_artifact(
                    task.id, "execution_result",
                    f"{task.title} - 执行结果",
                    content=result.content,
                    produced_by=agent.id,
                )
                bot.remember(f"完成任务 [{task.task_code}]: {task.title}。结果: {result.content[:300]}")
                await task_svc.mark_completed(task.id, result.content[:500], f"agent:{agent.id}")
                print(f"[AgentWorker] {agent.name} 完成 {task.task_code} (tokens={result.total_tokens})")
            else:
                await task_svc.mark_failed(task.id, result.error_message, f"agent:{agent.id}")
                print(f"[AgentWorker] {agent.name} 失败 {task.task_code}: {result.error_message}")
                # Retry if under max
                if task.retry_count < task.max_retries:
                    await task_svc.retry_task(task.id, f"agent:{agent.id}")

        await session.commit()


agent_worker = AgentWorker()
