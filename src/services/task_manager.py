import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.task import Task
from src.repositories.task_repo import TaskRepository
from src.repositories.agent_repo import AgentRepository
from src.repositories.organization_repo import DepartmentRepository
from src.core.exceptions import TaskNotFoundError, InvalidStateTransitionError, AgentNotFoundError
from src.core.config import settings


class TaskStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    NEEDS_CLARIFICATION = "needs_clarification"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


class TaskPriority(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# Valid transitions
VALID_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.PENDING: {TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED},
    TaskStatus.IN_PROGRESS: {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.NEEDS_CLARIFICATION, TaskStatus.BLOCKED, TaskStatus.CANCELLED},
    TaskStatus.FAILED: {TaskStatus.PENDING, TaskStatus.IN_PROGRESS, TaskStatus.COMPLETED, TaskStatus.CANCELLED, TaskStatus.NEEDS_CLARIFICATION},
    TaskStatus.NEEDS_CLARIFICATION: {TaskStatus.PENDING, TaskStatus.IN_PROGRESS, TaskStatus.COMPLETED, TaskStatus.CANCELLED},
    TaskStatus.BLOCKED: {TaskStatus.PENDING, TaskStatus.IN_PROGRESS, TaskStatus.COMPLETED, TaskStatus.CANCELLED},
    TaskStatus.CANCELLED: set(),
    TaskStatus.COMPLETED: set(),
}


@dataclass
class TaskCreate:
    title: str
    created_by: str
    description: str = ""
    priority: TaskPriority = TaskPriority.MEDIUM
    assigned_agent_id: uuid.UUID | None = None
    assigned_department_id: uuid.UUID | None = None
    creator_agent_id: uuid.UUID | None = None
    parent_task_id: uuid.UUID | None = None
    deadline: datetime | None = None
    timeout_seconds: int | None = None
    estimated_effort_minutes: int | None = None
    max_retries: int | None = None
    tags: list[str] = field(default_factory=list)


@dataclass
class TaskDecomposition:
    title: str
    description: str = ""
    assigned_agent_id: uuid.UUID | None = None
    assigned_department_id: uuid.UUID | None = None
    priority: TaskPriority = TaskPriority.MEDIUM
    depends_on_codes: list[str] = field(default_factory=list)


class TaskManagerService:
    def __init__(self, session: AsyncSession):
        self.repo = TaskRepository(session)
        self.agent_repo = AgentRepository(session)
        self.dept_repo = DepartmentRepository(session)
        self.session = session

    # ── 创建 ──────────────────────────────────────────

    async def create_task(self, data: TaskCreate) -> Task:
        if data.assigned_agent_id:
            agent = await self.agent_repo.get(data.assigned_agent_id)
            if not agent:
                raise AgentNotFoundError(f"Agent不存在: {data.assigned_agent_id}")

        parent_code = None
        root_id = None
        if data.parent_task_id:
            parent = await self.repo.get(data.parent_task_id)
            if not parent:
                raise TaskNotFoundError(f"父任务不存在: {data.parent_task_id}")
            parent_code = parent.task_code
            root_id = parent.root_task_id or parent.id

        task_code = await self.repo.generate_task_code(parent_code)
        max_retries = data.max_retries or settings.task_max_retries_default

        task = Task(
            task_code=task_code,
            parent_task_id=data.parent_task_id,
            root_task_id=root_id,
            title=data.title,
            description=data.description,
            status=TaskStatus.PENDING.value,
            priority=data.priority.value,
            assigned_agent_id=data.assigned_agent_id,
            assigned_department_id=data.assigned_department_id,
            created_by=data.created_by,
            creator_agent_id=data.creator_agent_id,
            deadline=data.deadline,
            timeout_seconds=data.timeout_seconds,
            estimated_effort_minutes=data.estimated_effort_minutes,
            max_retries=max_retries,
            tags=data.tags or [],
        )
        return await self.repo.create(task)

    async def decompose_task(self, parent_task_id: uuid.UUID, sub_tasks: list[TaskDecomposition], creator_agent_id: uuid.UUID | None = None) -> list[Task]:
        parent = await self.repo.get(parent_task_id)
        if not parent:
            raise TaskNotFoundError(f"父任务不存在: {parent_task_id}")

        created = []
        for sub in sub_tasks:
            child = await self.create_task(TaskCreate(
                title=sub.title,
                description=sub.description,
                created_by=f"agent:{creator_agent_id}" if creator_agent_id else "system",
                priority=sub.priority,
                assigned_agent_id=sub.assigned_agent_id,
                assigned_department_id=sub.assigned_department_id,
                creator_agent_id=creator_agent_id,
                parent_task_id=parent_task_id,
            ))
            created.append(child)

        for sub, child in zip(sub_tasks, created):
            for dep_code in sub.depends_on_codes:
                for other in created:
                    if other.task_code == dep_code:
                        await self.repo.add_dependency(child.id, other.id, "blocks")
                        break

        return created

    # ── 状态机 ──────────────────────────────────────────

    async def transition_status(self, task_id: uuid.UUID, new_status: TaskStatus, actor: str = "system") -> Task:
        task = await self.repo.get(task_id)
        if not task:
            raise TaskNotFoundError(f"任务不存在: {task_id}")

        current = TaskStatus(task.status)
        if new_status not in VALID_TRANSITIONS.get(current, set()):
            raise InvalidStateTransitionError(
                f"不允许的状态转换: {task.status} → {new_status.value}。允许的转换: {[s.value for s in VALID_TRANSITIONS.get(current, set())]}"
            )

        task.status = new_status.value

        if new_status == TaskStatus.IN_PROGRESS and task.started_at is None:
            task.started_at = datetime.now(timezone.utc)
        elif new_status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
            task.completed_at = datetime.now(timezone.utc)

        await self._audit_status_change(task, new_status, actor)
        return await self.repo.update(task)

    async def mark_in_progress(self, task_id: uuid.UUID, actor: str = "system") -> Task:
        return await self.transition_status(task_id, TaskStatus.IN_PROGRESS, actor)

    async def mark_completed(self, task_id: uuid.UUID, result_summary: str = "", actor: str = "system") -> Task:
        task = await self.repo.get(task_id)
        if not task:
            raise TaskNotFoundError(f"任务不存在: {task_id}")
        if result_summary:
            task.description = (task.description or "") + f"\n\n结果: {result_summary}"
            await self.repo.update(task)
        return await self.transition_status(task_id, TaskStatus.COMPLETED, actor)

    async def mark_failed(self, task_id: uuid.UUID, error_message: str = "", actor: str = "system") -> Task:
        task = await self.repo.get(task_id)
        if not task:
            raise TaskNotFoundError(f"任务不存在: {task_id}")
        task.status = TaskStatus.FAILED.value
        task.completed_at = datetime.now(timezone.utc)
        await self._audit_status_change(task, TaskStatus.FAILED, actor)
        return await self.repo.update(task)

    async def mark_needs_clarification(self, task_id: uuid.UUID, reason: str = "", actor: str = "system") -> Task:
        task = await self.repo.get(task_id)
        if not task:
            raise TaskNotFoundError(f"任务不存在: {task_id}")
        task.status = TaskStatus.NEEDS_CLARIFICATION.value
        await self._audit_status_change(task, TaskStatus.NEEDS_CLARIFICATION, actor)
        return await self.repo.update(task)

    async def mark_blocked(self, task_id: uuid.UUID, reason: str = "", actor: str = "system") -> Task:
        deps_satisfied = await self.repo.are_all_dependencies_satisfied(task_id)
        if not deps_satisfied:
            return await self.transition_status(task_id, TaskStatus.BLOCKED, actor)
        return await self.transition_status(task_id, TaskStatus.IN_PROGRESS, actor)

    async def cancel_task(self, task_id: uuid.UUID, actor: str = "system") -> Task:
        task = await self.repo.get(task_id)
        if not task:
            raise TaskNotFoundError(f"任务不存在: {task_id}")
        sub_tasks = await self.repo.list_sub_tasks(task_id)
        for sub in sub_tasks:
            if sub.status not in ("completed", "cancelled"):
                await self.cancel_task(sub.id, actor)
        return await self.transition_status(task_id, TaskStatus.CANCELLED, actor)

    # ── 重试 ──────────────────────────────────────────

    async def retry_task(self, task_id: uuid.UUID, actor: str = "system") -> Task:
        task = await self.repo.get(task_id)
        if not task:
            raise TaskNotFoundError(f"任务不存在: {task_id}")
        if task.retry_count >= task.max_retries:
            raise InvalidStateTransitionError(
                f"已达最大重试次数 ({task.max_retries})，任务需要升级"
            )
        task.retry_count += 1
        await self.repo.update(task)
        return await self.transition_status(task_id, TaskStatus.PENDING, actor)

    # ── 查询 ──────────────────────────────────────────

    async def get_task(self, task_id: uuid.UUID) -> Task:
        task = await self.repo.get(task_id)
        if not task:
            raise TaskNotFoundError(f"任务不存在: {task_id}")
        return task

    async def get_task_tree(self, task_id: uuid.UUID) -> dict:
        return await self.repo.get_task_tree(task_id)

    async def get_task_breadcrumb(self, task_id: uuid.UUID) -> list[dict]:
        task = await self.repo.get(task_id)
        if not task:
            raise TaskNotFoundError(f"任务不存在: {task_id}")
        breadcrumb = []
        current = task
        while current:
            breadcrumb.append({
                "id": str(current.id),
                "task_code": current.task_code,
                "title": current.title,
                "status": current.status,
            })
            if current.parent_task_id:
                current = await self.repo.get(current.parent_task_id)
            else:
                current = None
        return list(reversed(breadcrumb))

    async def list_tasks(self, status: str | None = None) -> list[Task]:
        return await self.repo.list_all(status=status)

    async def list_agent_tasks(self, agent_id: uuid.UUID) -> list[Task]:
        return await self.repo.list_by_agent(agent_id)

    # ── 依赖管理 ──────────────────────────────────────────

    async def add_dependency(self, task_id: uuid.UUID, depends_on_id: uuid.UUID, dep_type: str = "blocks"):
        await self.repo.add_dependency(task_id, depends_on_id, dep_type)

    async def get_blocked_tasks(self, agent_id: uuid.UUID | None = None) -> list[Task]:
        tasks = await self.repo.list_all(status=TaskStatus.BLOCKED.value)
        if agent_id:
            tasks = [t for t in tasks if t.assigned_agent_id == agent_id]
        return tasks

    # ── 审计 ──────────────────────────────────────────

    async def _audit_status_change(self, task: Task, new_status: TaskStatus, actor: str):
        from src.models.audit import AuditLog
        log = AuditLog(
            event_type="task.status_changed",
            entity_type="task",
            entity_id=task.id,
            actor=actor,
            action=f"任务状态变更: {task.status} → {new_status.value}",
            details={
                "task_code": task.task_code,
                "from_status": task.status,
                "to_status": new_status.value,
                "assigned_agent_id": str(task.assigned_agent_id) if task.assigned_agent_id else None,
            },
        )
        self.session.add(log)
