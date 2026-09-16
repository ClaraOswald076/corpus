import uuid
from dataclasses import dataclass
from enum import IntEnum, StrEnum
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.organization import Department
from src.repositories.agent_repo import AgentRepository
from src.repositories.organization_repo import DepartmentRepository
from src.core.exceptions import CircularDependencyError, DepartmentNotFoundError, OrganizationConstraintError


class OrgTier(IntEnum):
    T0 = 0
    T1 = 1
    T2 = 2


class DeptType(StrEnum):
    CEO_OFFICE = "ceo_office"
    DEPARTMENT = "department"
    CENTER = "center"
    SECTION = "section"
    OFFICE = "office"


VALID_TIER_TYPES: dict[OrgTier, set[DeptType]] = {
    OrgTier.T0: {DeptType.CEO_OFFICE},
    OrgTier.T1: {DeptType.DEPARTMENT},
    OrgTier.T2: {DeptType.CENTER, DeptType.SECTION, DeptType.OFFICE},
}

PERMISSION_MATRIX = {
    OrgTier.T0: {
        "can_create_task": True,
        "can_decompose_task": True,
        "can_escalate_to_user": True,
        "can_create_department": True,
        "can_delete_department": True,
        "can_approve_recruitment": True,
    },
    OrgTier.T1: {
        "can_create_task": True,
        "can_decompose_task": True,
        "can_escalate_to_user": False,
        "can_create_department": True,
        "can_delete_department": True,
        "can_approve_recruitment": True,
    },
    OrgTier.T2: {
        "can_create_task": True,
        "can_decompose_task": False,
        "can_escalate_to_user": False,
        "can_create_department": False,
        "can_delete_department": False,
        "can_approve_recruitment": False,
    },
}


@dataclass
class DepartmentCreate:
    name: str
    tier: OrgTier
    dept_type: DeptType
    parent_id: uuid.UUID | None = None
    description: str = ""
    dept_code: str | None = None
    head_agent_id: uuid.UUID | None = None
    sort_order: int = 0


@dataclass
class DepartmentUpdate:
    name: str | None = None
    description: str | None = None
    parent_id: uuid.UUID | None = None
    head_agent_id: uuid.UUID | None = None
    sort_order: int | None = None
    is_active: bool | None = None


class OrgStructureService:
    def __init__(self, session: AsyncSession):
        self.repo = DepartmentRepository(session)
        self.session = session

    async def create_department(self, data: DepartmentCreate) -> Department:
        self._validate_tier_type(data.tier, data.dept_type)

        if data.tier == OrgTier.T0:
            if data.parent_id is not None:
                raise OrganizationConstraintError("T0(CEO办公室)不能有上级部门")
            existing_t0 = await self.repo.list_by_tier(0)
            if existing_t0:
                raise OrganizationConstraintError("已存在T0层级部门，每个平台只能有一个CEO办公室")
        else:
            if data.parent_id is None:
                raise OrganizationConstraintError(f"T{data.tier.value}部门必须指定上级部门")
            parent = await self.repo.get(data.parent_id)
            if not parent:
                raise DepartmentNotFoundError(f"上级部门不存在: {data.parent_id}")
            if data.tier == OrgTier.T1 and parent.tier != OrgTier.T0:
                raise OrganizationConstraintError("T1部门的上级必须是T0")
            if data.tier == OrgTier.T2 and parent.tier != OrgTier.T1:
                raise OrganizationConstraintError("T2部门的上级必须是T1")

        org_path = await self._compute_org_path(data.name, data.parent_id)

        dept = Department(
            name=data.name,
            description=data.description,
            parent_id=data.parent_id,
            org_path=org_path,
            tier=data.tier.value,
            dept_type=data.dept_type.value,
            dept_code=data.dept_code,
            head_agent_id=data.head_agent_id,
            sort_order=data.sort_order,
        )
        dept = await self.repo.create(dept)
        return dept

    async def update_department(self, department_id: uuid.UUID, data: DepartmentUpdate) -> Department:
        dept = await self.repo.get(department_id)
        if not dept:
            raise DepartmentNotFoundError(f"部门不存在: {department_id}")

        if data.name is not None:
            dept.name = data.name
        if data.description is not None:
            dept.description = data.description
        if data.head_agent_id is not None:
            dept.head_agent_id = data.head_agent_id
        if data.sort_order is not None:
            dept.sort_order = data.sort_order
        if data.is_active is not None:
            dept.is_active = data.is_active

        if data.parent_id is not None:
            await self._move_department(dept, data.parent_id)

        return await self.repo.update(dept)

    async def move_department(self, department_id: uuid.UUID, new_parent_id: uuid.UUID) -> Department:
        dept = await self.repo.get(department_id)
        if not dept:
            raise DepartmentNotFoundError(f"部门不存在: {department_id}")
        await self._move_department(dept, new_parent_id)
        return await self.repo.update(dept)

    async def _move_department(self, dept: Department, new_parent_id: uuid.UUID):
        if dept.id == new_parent_id:
            raise CircularDependencyError("部门不能移动到自身下")

        new_parent = await self.repo.get(new_parent_id)
        if not new_parent:
            raise DepartmentNotFoundError(f"目标上级部门不存在: {new_parent_id}")

        if dept.tier == 0:
            raise OrganizationConstraintError("T0部门不能被移动")

        expected_parent_tier = dept.tier - 1
        if new_parent.tier != expected_parent_tier:
            raise OrganizationConstraintError(
                f"T{dept.tier}部门的上级必须是T{expected_parent_tier}，但目标部门是T{new_parent.tier}"
            )

        await self.repo.check_circular_parent(dept.id, new_parent_id)

        dept.parent_id = new_parent_id
        dept.org_path = await self._compute_org_path(dept.name, new_parent_id)

        children = await self.repo.list_children(dept.id)
        for child in children:
            child.org_path = f"{dept.org_path}/{child.name.lower().replace(' ', '_')}"
            await self.repo.update(child)

    async def delete_department(self, department_id: uuid.UUID):
        dept = await self.repo.get(department_id)
        if not dept:
            raise DepartmentNotFoundError(f"部门不存在: {department_id}")

        children = await self.repo.list_children(department_id)
        if children:
            raise OrganizationConstraintError(f"部门 '{dept.name}' 下还有 {len(children)} 个子部门，请先移除子部门")

        # 辖下 agent 不挡道就删：ORM 的 delete 会把已加载子 agent 的 FK 置 NULL，
        # 撞 NOT NULL 约束炸出来的 IntegrityError 对用户毫无可读性。
        occupants = await AgentRepository(self.session).list_by_department(department_id)
        if occupants:
            raise OrganizationConstraintError(f"部门 '{dept.name}' 下还有 {len(occupants)} 名 agent，请先转移或删除")

        await self.repo.delete(dept)

    async def get_department(self, department_id: uuid.UUID) -> Department:
        dept = await self.repo.get(department_id)
        if not dept:
            raise DepartmentNotFoundError(f"部门不存在: {department_id}")
        return dept

    async def list_departments(self) -> list[Department]:
        return await self.repo.list_all()

    async def get_org_tree(self) -> list[dict]:
        depts = await self.repo.list_all()
        dept_map = {d.id: d for d in depts}
        roots = [d for d in depts if d.parent_id is None]

        def build_tree(dept: Department) -> dict:
            children = [d for d in depts if d.parent_id == dept.id]
            return {
                "id": str(dept.id),
                "name": dept.name,
                "tier": dept.tier,
                "dept_type": dept.dept_type,
                "dept_code": dept.dept_code,
                "org_path": dept.org_path,
                "head_agent_id": str(dept.head_agent_id) if dept.head_agent_id else None,
                "is_active": dept.is_active,
                "children": [build_tree(c) for c in sorted(children, key=lambda x: x.sort_order)],
            }

        return [build_tree(r) for r in roots]

    def get_effective_permissions(self, tier: int, agent_permissions: set | None = None) -> dict:
        tier_perms = PERMISSION_MATRIX.get(OrgTier(tier), {})
        if agent_permissions is None:
            return tier_perms
        return {k: v and k in agent_permissions for k, v in tier_perms.items()}

    def _validate_tier_type(self, tier: OrgTier, dept_type: DeptType):
        allowed = VALID_TIER_TYPES.get(tier, set())
        if dept_type not in allowed:
            allowed_str = ", ".join(t.value for t in allowed)
            raise OrganizationConstraintError(f"T{tier.value}层级不允许dept_type={dept_type.value}，允许类型: {allowed_str}")

    async def _compute_org_path(self, name: str, parent_id: uuid.UUID | None) -> str:
        if parent_id is None:
            return f"/{name.lower().replace(' ', '_')}"
        parent = await self.repo.get(parent_id)
        if not parent:
            raise DepartmentNotFoundError(f"上级部门不存在: {parent_id}")
        slug = name.lower().replace(" ", "_").replace("/", "_")
        return f"{parent.org_path}/{slug}"
