import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from src.api.deps import get_db
from src.services.agent_lifecycle import AgentLifecycleService, AgentCreate

router = APIRouter()


class AgentCreateRequest(BaseModel):
    name: str
    role: str
    department_id: str = ""
    department_name: str = ""  # Alternative: resolve by name
    model_preset_id: str | None = None
    preset_name: str = ""  # Alternative
    system_prompt: str | None = None
    max_retries: int = 3
    temperature: float = 0.7
    max_tokens: int = 4096
    max_memory_tokens: int = 100000
    reports_to_agent_id: str | None = None
    reports_to: str = ""  # Alternative: resolve by name
    soul_content: str = ""
    memory_content: str = ""


class AgentUpdateSoulRequest(BaseModel):
    content: str


@router.get("/")
async def list_agents(db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from src.models.organization import Agent as AgentModel
    result = await db.execute(
        select(AgentModel).options(selectinload(AgentModel.department), selectinload(AgentModel.model_preset))
    )
    agents = result.scalars().all()
    return [
        {
            "id": str(a.id),
            "name": a.name,
            "role": a.role,
            "department_id": str(a.department_id),
            "model_preset_id": str(a.model_preset_id) if a.model_preset_id else None,
            "agent_folder_path": a.agent_folder_path,
            "is_active": a.is_active,
            "availability_status": a.availability_status,
            "tier": a.department.tier if a.department else None,
            "department_name": a.department.name if a.department else "",
            "preset_name": a.model_preset.name if a.model_preset else "",
        }
        for a in agents
    ]


@router.post("/", status_code=201)
async def create_agent(data: AgentCreateRequest, db: AsyncSession = Depends(get_db)):
    svc = AgentLifecycleService(db)
    try:
        from src.repositories.organization_repo import DepartmentRepository
        from src.repositories.agent_repo import AgentRepository, ModelPresetRepository
        dept_repo = DepartmentRepository(db)
        agent_repo = AgentRepository(db)
        preset_repo = ModelPresetRepository(db)

        # Resolve department
        dept_id = None
        if data.department_id:
            dept_id = uuid.UUID(data.department_id)
        elif data.department_name:
            d = await dept_repo.get_by_name(data.department_name)
            if d: dept_id = d.id
        if not dept_id:
            raise HTTPException(status_code=400, detail="部门不能为空")

        # Resolve preset
        preset_id = None
        if data.model_preset_id:
            preset_id = uuid.UUID(data.model_preset_id)
        elif data.preset_name:
            p = await preset_repo.get_by_name(data.preset_name)
            if p: preset_id = p.id

        # Resolve reports_to
        reports_to_id = None
        if data.reports_to_agent_id:
            reports_to_id = uuid.UUID(data.reports_to_agent_id)
        elif data.reports_to:
            a = await agent_repo.get_by_name(data.reports_to)
            if a: reports_to_id = a.id

        agent = await svc.create_agent(AgentCreate(
            name=data.name,
            role=data.role,
            department_id=dept_id,
            model_preset_id=preset_id,
            system_prompt=data.system_prompt,
            max_retries=data.max_retries,
            temperature=data.temperature,
            max_tokens=data.max_tokens,
            max_memory_tokens=data.max_memory_tokens,
            reports_to_agent_id=reports_to_id,
            soul_content=data.soul_content,
            memory_content=data.memory_content,
        ))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "id": str(agent.id),
        "name": agent.name,
        "role": agent.role,
        "agent_folder_path": agent.agent_folder_path,
        "message": "Agent已创建",
    }


@router.get("/{agent_id}")
async def get_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    svc = AgentLifecycleService(db)
    try:
        agent = await svc.get_agent(uuid.UUID(agent_id))
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
    from src.utils.file_system import read_agent_soul, read_agent_memory
    from src.core.config import settings
    full_path = settings.project_root / agent.agent_folder_path
    return {
        "id": str(agent.id),
        "name": agent.name,
        "role": agent.role,
        "department_id": str(agent.department_id),
        "model_preset_id": str(agent.model_preset_id) if agent.model_preset_id else None,
        "reports_to_agent_id": str(agent.reports_to_agent_id) if agent.reports_to_agent_id else None,
        "agent_folder_path": agent.agent_folder_path,
        "system_prompt": agent.system_prompt,
        "is_active": agent.is_active,
        "availability_status": agent.availability_status,
        "max_memory_tokens": agent.max_memory_tokens,
        "temperature": agent.temperature,
        "max_tokens": agent.max_tokens,
        "soul_content": read_agent_soul(str(full_path)),
        "memory_content": read_agent_memory(str(full_path)),
    }


class AgentUpdateRequest(BaseModel):
    model_preset_id: str | None = None
    model_preset_name: str = ""
    temperature: float | None = None
    max_tokens: int | None = None
    max_memory_tokens: int | None = None
    is_active: bool | None = None
    system_prompt: str | None = None


@router.put("/{agent_id}")
async def update_agent(agent_id: uuid.UUID, data: AgentUpdateRequest, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from src.models.organization import Agent as AgentModel
    from src.repositories.agent_repo import ModelPresetRepository
    result = await db.execute(
        select(AgentModel).options(selectinload(AgentModel.department), selectinload(AgentModel.model_preset))
        .where(AgentModel.id == agent_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent不存在")

    if data.is_active is not None:
        agent.is_active = data.is_active
        agent.availability_status = "available" if data.is_active else "offline"
    if data.temperature is not None:
        agent.temperature = data.temperature
    if data.max_tokens is not None:
        agent.max_tokens = data.max_tokens
    if data.max_memory_tokens is not None:
        agent.max_memory_tokens = data.max_memory_tokens
    if data.system_prompt is not None:
        agent.system_prompt = data.system_prompt

    if data.model_preset_id:
        agent.model_preset_id = uuid.UUID(data.model_preset_id)
    elif data.model_preset_name:
        preset_repo = ModelPresetRepository(db)
        p = await preset_repo.get_by_name(data.model_preset_name)
        if p:
            agent.model_preset_id = p.id

    await db.flush()
    return {"id": str(agent.id), "name": agent.name, "message": "Agent已更新",
            "is_active": agent.is_active, "temperature": agent.temperature,
            "max_tokens": agent.max_tokens,
            "preset_name": agent.model_preset.name if agent.model_preset else ""}


@router.post("/{agent_id}/deactivate")
async def deactivate_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    svc = AgentLifecycleService(db)
    try:
        agent = await svc.deactivate_agent(uuid.UUID(agent_id))
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"id": str(agent.id), "name": agent.name, "is_active": agent.is_active, "message": "Agent已停用"}


@router.delete("/{agent_id}")
async def delete_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    svc = AgentLifecycleService(db)
    try:
        await svc.delete_agent(uuid.UUID(agent_id))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"message": "Agent已删除"}


@router.get("/{agent_id}/soul")
async def get_agent_soul(agent_id: str, db: AsyncSession = Depends(get_db)):
    svc = AgentLifecycleService(db)
    try:
        agent = await svc.get_agent(uuid.UUID(agent_id))
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
    from src.utils.file_system import read_agent_soul
    from src.core.config import settings
    full_path = settings.project_root / agent.agent_folder_path
    return {"agent_name": agent.name, "soul_content": read_agent_soul(str(full_path))}


@router.put("/{agent_id}/soul")
async def update_agent_soul(agent_id: str, data: AgentUpdateSoulRequest, db: AsyncSession = Depends(get_db)):
    svc = AgentLifecycleService(db)
    try:
        agent = await svc.get_agent(uuid.UUID(agent_id))
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
    from src.utils.file_system import write_agent_soul
    from src.core.config import settings
    full_path = settings.project_root / agent.agent_folder_path
    write_agent_soul(str(full_path), data.content)
    await svc.sync_soul(uuid.UUID(agent_id))
    return {"agent_name": agent.name, "message": "soul.md已更新"}


@router.get("/{agent_id}/memory")
async def get_agent_memory(agent_id: str, db: AsyncSession = Depends(get_db)):
    svc = AgentLifecycleService(db)
    try:
        agent = await svc.get_agent(uuid.UUID(agent_id))
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
    from src.utils.file_system import read_agent_memory
    from src.core.config import settings
    full_path = settings.project_root / agent.agent_folder_path
    return {"agent_name": agent.name, "memory_content": read_agent_memory(str(full_path))}
