import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.organization import Department
from src.core.exceptions import CircularDependencyError


class DepartmentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, department_id: uuid.UUID) -> Department | None:
        return await self.session.get(Department, department_id)

    async def get_by_name(self, name: str) -> Department | None:
        result = await self.session.execute(select(Department).where(Department.name == name))
        return result.scalar_one_or_none()

    async def list_all(self, active_only: bool = True) -> list[Department]:
        stmt = select(Department).order_by(Department.tier, Department.sort_order)
        if active_only:
            stmt = stmt.where(Department.is_active == True)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_tier(self, tier: int) -> list[Department]:
        result = await self.session.execute(
            select(Department).where(Department.tier == tier, Department.is_active == True)
        )
        return list(result.scalars().all())

    async def list_children(self, parent_id: uuid.UUID) -> list[Department]:
        result = await self.session.execute(
            select(Department).where(Department.parent_id == parent_id, Department.is_active == True)
        )
        return list(result.scalars().all())

    async def create(self, department: Department) -> Department:
        self.session.add(department)
        await self.session.flush()
        return department

    async def update(self, department: Department) -> Department:
        await self.session.flush()
        return department

    async def delete(self, department: Department):
        await self.session.delete(department)
        await self.session.flush()

    async def check_circular_parent(self, department_id: uuid.UUID, new_parent_id: uuid.UUID) -> bool:
        visited = set()
        current = new_parent_id
        while current:
            if current == department_id:
                raise CircularDependencyError(f"将部门 {department_id} 移动到 {new_parent_id} 会导致循环依赖")
            if current in visited:
                raise CircularDependencyError("检测到部门层级环")
            visited.add(current)
            dept = await self.get(current)
            if dept is None:
                break
            current = dept.parent_id
        return False
