import uuid
from datetime import datetime, timezone
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.task import Task, TaskDependency, TaskArtifact
from src.core.exceptions import CircularDependencyError, TaskNotFoundError


class TaskRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, task_id: uuid.UUID) -> Task | None:
        return await self.session.get(Task, task_id)

    async def get_by_code(self, task_code: str) -> Task | None:
        result = await self.session.execute(select(Task).where(Task.task_code == task_code))
        return result.scalar_one_or_none()

    async def list_all(self, status: str | None = None, limit: int = 100) -> list[Task]:
        stmt = select(Task).order_by(Task.created_at.desc()).limit(limit)
        if status:
            stmt = stmt.where(Task.status == status)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_agent(self, agent_id: uuid.UUID, limit: int = 50) -> list[Task]:
        result = await self.session.execute(
            select(Task).where(Task.assigned_agent_id == agent_id).order_by(Task.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def list_by_department(self, department_id: uuid.UUID, limit: int = 50) -> list[Task]:
        result = await self.session.execute(
            select(Task).where(Task.assigned_department_id == department_id).order_by(Task.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def list_sub_tasks(self, parent_task_id: uuid.UUID) -> list[Task]:
        result = await self.session.execute(
            select(Task).where(Task.parent_task_id == parent_task_id).order_by(Task.created_at)
        )
        return list(result.scalars().all())

    async def list_root_tasks(self, limit: int = 50) -> list[Task]:
        result = await self.session.execute(
            select(Task).where(Task.parent_task_id.is_(None)).order_by(Task.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def create(self, task: Task) -> Task:
        self.session.add(task)
        await self.session.flush()
        return task

    async def update(self, task: Task) -> Task:
        await self.session.flush()
        return task

    async def delete(self, task: Task):
        await self.session.delete(task)
        await self.session.flush()

    async def generate_task_code(self, parent_code: str | None = None) -> str:
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        if parent_code is None:
            result = await self.session.execute(
                select(func.count(Task.id)).where(
                    Task.task_code.like(f"T-{today}-%"),
                    Task.parent_task_id.is_(None),
                )
            )
            count = result.scalar() or 0
            return f"T-{today}-{count + 1:03d}"
        else:
            result = await self.session.execute(
                select(func.count(Task.id)).where(Task.task_code.like(f"{parent_code}-%"))
            )
            count = result.scalar() or 0
            return f"{parent_code}-{count + 1:03d}"

    async def check_circular_dependency(self, task_id: uuid.UUID, depends_on_id: uuid.UUID):
        if task_id == depends_on_id:
            raise CircularDependencyError("任务不能依赖自身")
        visited = set()
        to_visit = [depends_on_id]
        while to_visit:
            current = to_visit.pop()
            if current == task_id:
                raise CircularDependencyError(f"创建此依赖会导致循环: {task_id} → ... → {depends_on_id} → {task_id}")
            if current in visited:
                continue
            visited.add(current)
            deps = await self.get_dependencies(current)
            for dep in deps:
                to_visit.append(dep.depends_on_task_id)

    async def add_dependency(self, task_id: uuid.UUID, depends_on_id: uuid.UUID, dep_type: str = "blocks") -> TaskDependency:
        await self.check_circular_dependency(task_id, depends_on_id)
        dep = TaskDependency(task_id=task_id, depends_on_task_id=depends_on_id, dependency_type=dep_type)
        self.session.add(dep)
        await self.session.flush()
        return dep

    async def get_dependencies(self, task_id: uuid.UUID) -> list[TaskDependency]:
        result = await self.session.execute(
            select(TaskDependency).where(TaskDependency.task_id == task_id)
        )
        return list(result.scalars().all())

    async def get_dependents(self, task_id: uuid.UUID) -> list[TaskDependency]:
        result = await self.session.execute(
            select(TaskDependency).where(TaskDependency.depends_on_task_id == task_id)
        )
        return list(result.scalars().all())

    async def are_all_dependencies_satisfied(self, task_id: uuid.UUID) -> bool:
        deps = await self.get_dependencies(task_id)
        for dep in deps:
            dep_task = await self.get(dep.depends_on_task_id)
            if dep_task and dep_task.status != "completed":
                return False
        return True

    async def create_artifact(self, task_id: uuid.UUID, artifact_type: str, title: str, content: str = "", file_path: str = "", produced_by: uuid.UUID | None = None) -> TaskArtifact:
        artifact = TaskArtifact(
            task_id=task_id, artifact_type=artifact_type, title=title,
            content=content, file_path=file_path or None, produced_by_agent_id=produced_by,
        )
        self.session.add(artifact)
        await self.session.flush()
        return artifact

    async def get_artifacts(self, task_id: uuid.UUID) -> list[TaskArtifact]:
        result = await self.session.execute(
            select(TaskArtifact).where(TaskArtifact.task_id == task_id).order_by(TaskArtifact.created_at)
        )
        return list(result.scalars().all())

    async def get_task_tree(self, task_id: uuid.UUID) -> dict:
        task = await self.get(task_id)
        if not task:
            raise TaskNotFoundError(f"任务不存在: {task_id}")
        sub_tasks = await self.list_sub_tasks(task_id)
        deps = await self.get_dependencies(task_id)
        artifacts = await self.get_artifacts(task_id)
        return {
            "task": task,
            "sub_tasks": sub_tasks,
            "dependencies": deps,
            "artifacts": artifacts,
            "children": [await self.get_task_tree(st.id) for st in sub_tasks],
        }
