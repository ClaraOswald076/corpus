import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from src.api.deps import get_db
from src.services.task_manager import TaskManagerService, TaskCreate, TaskDecomposition, TaskStatus, TaskPriority

router = APIRouter()


class TaskCreateRequest(BaseModel):
    title: str
    description: str = ""
    priority: str = "medium"
    assigned_agent_id: str | None = None
    assign_to: str = ""  # Alternative: agent name
    assigned_department_id: str | None = None
    parent_task_id: str | None = None
    parent_code: str = ""  # Alternative: task code
    deadline: str | None = None
    timeout_seconds: int | None = None
    max_retries: int | None = None
    tags: list[str] = []
    created_by: str = "user"


class TaskDecomposeRequest(BaseModel):
    sub_tasks: list[dict]  # [{"title":"...", "description":"...", "assigned_agent_id":"...", "priority":"medium"}]


class TaskStatusUpdateRequest(BaseModel):
    status: str
    reason: str = ""


class TaskDependencyRequest(BaseModel):
    depends_on_task_id: str
    dependency_type: str = "blocks"


@router.get("/")
async def list_tasks(status: str | None = None, db: AsyncSession = Depends(get_db)):
    svc = TaskManagerService(db)
    tasks = await svc.list_tasks(status=status)
    return [_task_to_dict(t) for t in tasks]


@router.get("/roots")
async def list_root_tasks(db: AsyncSession = Depends(get_db)):
    from src.repositories.task_repo import TaskRepository
    repo = TaskRepository(db)
    tasks = await repo.list_root_tasks()
    return [_task_to_dict(t) for t in tasks]


@router.post("/", status_code=201)
async def create_task(data: TaskCreateRequest, db: AsyncSession = Depends(get_db)):
    svc = TaskManagerService(db)
    try:
        from src.repositories.agent_repo import AgentRepository
        from src.repositories.task_repo import TaskRepository

        # Resolve agent
        agent_id = None
        if data.assigned_agent_id:
            agent_id = uuid.UUID(data.assigned_agent_id)
        elif data.assign_to:
            agent_repo = AgentRepository(db)
            a = await agent_repo.get_by_name(data.assign_to)
            if a: agent_id = a.id

        # Resolve parent task
        parent_id = None
        if data.parent_task_id:
            parent_id = uuid.UUID(data.parent_task_id)
        elif data.parent_code:
            task_repo = TaskRepository(db)
            p = await task_repo.get_by_code(data.parent_code)
            if p: parent_id = p.id

        task = await svc.create_task(TaskCreate(
            title=data.title,
            description=data.description,
            created_by=data.created_by,
            priority=TaskPriority(data.priority),
            assigned_agent_id=agent_id,
            assigned_department_id=uuid.UUID(data.assigned_department_id) if data.assigned_department_id else None,
            parent_task_id=parent_id,
            deadline=datetime.fromisoformat(data.deadline) if data.deadline else None,
            timeout_seconds=data.timeout_seconds,
            max_retries=data.max_retries,
            tags=data.tags,
        ))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {**_task_to_dict(task), "message": "任务已创建"}


@router.get("/{task_id}")
async def get_task(task_id: str, db: AsyncSession = Depends(get_db)):
    svc = TaskManagerService(db)
    try:
        task = await svc.get_task(uuid.UUID(task_id))
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _task_to_dict(task)


@router.get("/{task_id}/tree")
async def get_task_tree(task_id: str, db: AsyncSession = Depends(get_db)):
    svc = TaskManagerService(db)
    try:
        tree = await svc.get_task_tree(uuid.UUID(task_id))
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _tree_to_dict(tree)


@router.get("/{task_id}/breadcrumb")
async def get_task_breadcrumb(task_id: str, db: AsyncSession = Depends(get_db)):
    svc = TaskManagerService(db)
    try:
        return await svc.get_task_breadcrumb(uuid.UUID(task_id))
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{task_id}/status")
async def update_task_status(task_id: str, data: TaskStatusUpdateRequest, db: AsyncSession = Depends(get_db)):
    svc = TaskManagerService(db)
    try:
        status_map = {
            "in_progress": lambda: svc.mark_in_progress(uuid.UUID(task_id)),
            "completed": lambda: svc.mark_completed(uuid.UUID(task_id), data.reason),
            "failed": lambda: svc.mark_failed(uuid.UUID(task_id), data.reason),
            "needs_clarification": lambda: svc.mark_needs_clarification(uuid.UUID(task_id), data.reason),
            "blocked": lambda: svc.mark_blocked(uuid.UUID(task_id), data.reason),
            "cancelled": lambda: svc.cancel_task(uuid.UUID(task_id)),
            "retry": lambda: svc.retry_task(uuid.UUID(task_id)),
        }
        handler = status_map.get(data.status)
        if not handler:
            raise HTTPException(status_code=400, detail=f"不支持的状态: {data.status}")
        task = await handler()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {**_task_to_dict(task), "message": f"状态已更新为 {task.status}"}


@router.post("/{task_id}/decompose")
async def decompose_task(task_id: str, data: TaskDecomposeRequest, db: AsyncSession = Depends(get_db)):
    svc = TaskManagerService(db)
    try:
        sub_tasks = [
            TaskDecomposition(
                title=st["title"],
                description=st.get("description", ""),
                assigned_agent_id=uuid.UUID(st["assigned_agent_id"]) if st.get("assigned_agent_id") else None,
                assigned_department_id=uuid.UUID(st["assigned_department_id"]) if st.get("assigned_department_id") else None,
                priority=TaskPriority(st.get("priority", "medium")),
                depends_on_codes=st.get("depends_on_codes", []),
            )
            for st in data.sub_tasks
        ]
        created = await svc.decompose_task(uuid.UUID(task_id), sub_tasks)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "parent_task_id": task_id,
        "sub_tasks": [_task_to_dict(t) for t in created],
        "count": len(created),
    }


@router.post("/{task_id}/dependencies")
async def add_task_dependency(task_id: str, data: TaskDependencyRequest, db: AsyncSession = Depends(get_db)):
    svc = TaskManagerService(db)
    try:
        await svc.add_dependency(
            uuid.UUID(task_id),
            uuid.UUID(data.depends_on_task_id),
            data.dependency_type,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"message": "依赖已添加"}


@router.get("/agent/{agent_id}")
async def list_agent_tasks(agent_id: str, db: AsyncSession = Depends(get_db)):
    svc = TaskManagerService(db)
    tasks = await svc.list_agent_tasks(uuid.UUID(agent_id))
    return [_task_to_dict(t) for t in tasks]


def _task_to_dict(task) -> dict:
    return {
        "id": str(task.id),
        "task_code": task.task_code,
        "parent_task_id": str(task.parent_task_id) if task.parent_task_id else None,
        "root_task_id": str(task.root_task_id) if task.root_task_id else None,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "priority": task.priority,
        "assigned_agent_id": str(task.assigned_agent_id) if task.assigned_agent_id else None,
        "assigned_department_id": str(task.assigned_department_id) if task.assigned_department_id else None,
        "created_by": task.created_by,
        "retry_count": task.retry_count,
        "max_retries": task.max_retries,
        "escalation_level": task.escalation_level,
        "deadline": task.deadline.isoformat() if task.deadline else None,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
    }


def _tree_to_dict(node: dict) -> dict:
    task = node["task"]
    return {
        **_task_to_dict(task),
        "dependencies": [{"id": str(d.id), "depends_on": str(d.depends_on_task_id), "type": d.dependency_type} for d in node.get("dependencies", [])],
        "artifacts": [{"id": str(a.id), "type": a.artifact_type, "title": a.title} for a in node.get("artifacts", [])],
        "children": [_tree_to_dict(c) for c in node.get("children", [])],
    }
