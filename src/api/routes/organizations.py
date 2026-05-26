import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, field_validator
from src.api.deps import get_db
from src.services.org_structure import OrgStructureService, DepartmentCreate, DepartmentUpdate, OrgTier, DeptType

router = APIRouter()


class DepartmentCreateRequest(BaseModel):
    name: str
    tier: int
    dept_type: str
    parent_id: str | None = None
    parent_name: str = ""  # Alternative: resolve by name
    description: str = ""
    dept_code: str | None = None
    sort_order: int = 0

    @field_validator("tier")
    @classmethod
    def validate_tier(cls, v: int) -> int:
        if v not in (0, 1, 2):
            raise ValueError("tier 必须是 0、1 或 2")
        return v

    @field_validator("dept_type")
    @classmethod
    def validate_dept_type(cls, v: str) -> str:
        valid = ["ceo_office", "department", "center", "section", "office"]
        if v not in valid:
            raise ValueError(f"dept_type 必须是: {', '.join(valid)}")
        return v


class DepartmentUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    parent_id: str | None = None
    head_agent_id: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None


class DepartmentResponse(BaseModel):
    id: str
    name: str
    tier: int
    dept_type: str
    parent_id: str | None
    org_path: str
    dept_code: str | None
    head_agent_id: str | None
    is_active: bool
    description: str | None

    model_config = {"from_attributes": True}


@router.get("/tree")
async def get_org_tree(db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from src.models.organization import Agent as AgentModel
    result = await db.execute(
        select(AgentModel).options(selectinload(AgentModel.department), selectinload(AgentModel.model_preset))
    )
    agents = result.scalars().all()
    agent_map: dict = {}
    for a in agents:
        dept_id_str = str(a.department_id)
        if dept_id_str not in agent_map:
            agent_map[dept_id_str] = []
        agent_map[dept_id_str].append({
            "id": str(a.id), "name": a.name, "role": a.role,
            "is_active": a.is_active,
            "preset": a.model_preset.name if a.model_preset else "",
        })

    svc = OrgStructureService(db)
    tree = await svc.get_org_tree()

    def attach_agents(nodes):
        for n in nodes:
            n["agents"] = agent_map.get(n["id"], [])
            attach_agents(n.get("children", []))
    attach_agents(tree)
    return tree


@router.get("/")
async def list_departments(db: AsyncSession = Depends(get_db)):
    svc = OrgStructureService(db)
    depts = await svc.list_departments()
    return [
        {
            "id": str(d.id),
            "name": d.name,
            "tier": d.tier,
            "dept_type": d.dept_type,
            "parent_id": str(d.parent_id) if d.parent_id else None,
            "org_path": d.org_path,
            "dept_code": d.dept_code,
            "head_agent_id": str(d.head_agent_id) if d.head_agent_id else None,
            "is_active": d.is_active,
            "description": d.description,
        }
        for d in depts
    ]


@router.get("/{department_id}")
async def get_department(department_id: str, db: AsyncSession = Depends(get_db)):
    svc = OrgStructureService(db)
    try:
        dept = await svc.get_department(uuid.UUID(department_id))
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {
        "id": str(dept.id),
        "name": dept.name,
        "tier": dept.tier,
        "dept_type": dept.dept_type,
        "parent_id": str(dept.parent_id) if dept.parent_id else None,
        "org_path": dept.org_path,
        "dept_code": dept.dept_code,
        "head_agent_id": str(dept.head_agent_id) if dept.head_agent_id else None,
        "is_active": dept.is_active,
        "description": dept.description,
    }


@router.post("/", status_code=201)
async def create_department(data: DepartmentCreateRequest, db: AsyncSession = Depends(get_db)):
    svc = OrgStructureService(db)
    try:
        parent_id = None
        if data.parent_id:
            parent_id = uuid.UUID(data.parent_id)
        elif data.parent_name:
            from src.repositories.organization_repo import DepartmentRepository
            dept_repo = DepartmentRepository(db)
            parent = await dept_repo.get_by_name(data.parent_name)
            if parent:
                parent_id = parent.id
        dept = await svc.create_department(DepartmentCreate(
            name=data.name,
            tier=OrgTier(data.tier),
            dept_type=DeptType(data.dept_type),
            parent_id=parent_id,
            description=data.description,
            dept_code=data.dept_code,
            sort_order=data.sort_order,
        ))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"id": str(dept.id), "name": dept.name, "tier": dept.tier, "org_path": dept.org_path}


@router.put("/{department_id}")
async def update_department(department_id: str, data: DepartmentUpdateRequest, db: AsyncSession = Depends(get_db)):
    svc = OrgStructureService(db)
    try:
        dept = await svc.update_department(uuid.UUID(department_id), DepartmentUpdate(
            name=data.name,
            description=data.description,
            parent_id=uuid.UUID(data.parent_id) if data.parent_id else None,
            head_agent_id=uuid.UUID(data.head_agent_id) if data.head_agent_id else None,
            sort_order=data.sort_order,
            is_active=data.is_active,
        ))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"id": str(dept.id), "name": dept.name, "message": "更新成功"}


@router.delete("/{department_id}")
async def delete_department(department_id: str, db: AsyncSession = Depends(get_db)):
    svc = OrgStructureService(db)
    try:
        await svc.delete_department(uuid.UUID(department_id))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"message": "部门已删除"}


@router.post("/{department_id}/move/{new_parent_id}")
async def move_department(department_id: str, new_parent_id: str, db: AsyncSession = Depends(get_db)):
    svc = OrgStructureService(db)
    try:
        dept = await svc.move_department(uuid.UUID(department_id), uuid.UUID(new_parent_id))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"id": str(dept.id), "name": dept.name, "new_parent_id": new_parent_id, "message": "移动成功"}
