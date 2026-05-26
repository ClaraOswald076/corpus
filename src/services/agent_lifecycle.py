import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.organization import Agent, Department
from src.models.agent import SoulDocument
from src.repositories.agent_repo import AgentRepository, SoulDocumentRepository
from src.repositories.organization_repo import DepartmentRepository
from src.utils.file_system import create_agent_folder, delete_agent_folder, read_agent_soul, get_soul_last_modified
from src.core.config import settings
from src.core.exceptions import AgentNotFoundError, DepartmentNotFoundError, PlatformError


@dataclass
class AgentCreate:
    name: str
    role: str
    department_id: uuid.UUID
    model_preset_id: uuid.UUID | None = None
    system_prompt: str | None = None
    max_retries: int = 3
    temperature: float = 0.7
    max_tokens: int = 4096
    max_memory_tokens: int = 100000
    reports_to_agent_id: uuid.UUID | None = None
    soul_content: str = ""
    memory_content: str = ""
    capabilities: list[str] | None = None


class AgentLifecycleService:
    def __init__(self, session: AsyncSession):
        self.agent_repo = AgentRepository(session)
        self.dept_repo = DepartmentRepository(session)
        self.soul_repo = SoulDocumentRepository(session)
        self.session = session

    async def create_agent(self, data: AgentCreate) -> Agent:
        existing = await self.agent_repo.get_by_name(data.name)
        if existing:
            raise PlatformError(f"Agent '{data.name}' 已存在")

        department = await self.dept_repo.get(data.department_id)
        if not department:
            raise DepartmentNotFoundError(f"部门不存在: {data.department_id}")

        dept_name = department.name if department else "unknown"
        folder_path = create_agent_folder(dept_name, data.name, data.soul_content, data.memory_content)
        relative_path = str(folder_path.relative_to(settings.project_root))

        agent = Agent(
            name=data.name,
            role=data.role,
            department_id=data.department_id,
            reports_to_agent_id=data.reports_to_agent_id,
            model_preset_id=data.model_preset_id,
            agent_folder_path=relative_path,
            system_prompt=data.system_prompt or "",
            max_retries=data.max_retries,
            temperature=data.temperature,
            max_tokens=data.max_tokens,
            max_memory_tokens=data.max_memory_tokens,
        )
        agent = await self.agent_repo.create(agent)

        full_folder_path = settings.project_root / relative_path
        soul_content = read_agent_soul(str(full_folder_path))
        soul_doc = SoulDocument(
            agent_id=agent.id,
            content=soul_content,
            file_last_modified=get_soul_last_modified(str(full_folder_path)),
            last_edited_by="system",
        )
        await self.soul_repo.create(soul_doc)

        return agent

    async def deactivate_agent(self, agent_id: uuid.UUID) -> Agent:
        agent = await self.agent_repo.get(agent_id)
        if not agent:
            raise AgentNotFoundError(f"Agent不存在: {agent_id}")
        agent.is_active = False
        agent.availability_status = "offline"
        return await self.agent_repo.update(agent)

    async def delete_agent(self, agent_id: uuid.UUID):
        agent = await self.agent_repo.get(agent_id)
        if not agent:
            raise AgentNotFoundError(f"Agent不存在: {agent_id}")
        full_path = settings.project_root / agent.agent_folder_path
        delete_agent_folder(str(full_path))
        await self.agent_repo.delete(agent)

    async def get_agent(self, agent_id: uuid.UUID) -> Agent:
        agent = await self.agent_repo.get(agent_id)
        if not agent:
            raise AgentNotFoundError(f"Agent不存在: {agent_id}")
        return agent

    async def list_agents(self) -> list[Agent]:
        return await self.agent_repo.list_all()

    async def sync_soul(self, agent_id: uuid.UUID):
        agent = await self.get_agent(agent_id)
        full_path = settings.project_root / agent.agent_folder_path
        current_content = read_agent_soul(str(full_path))
        current_mtime = get_soul_last_modified(str(full_path))

        soul_doc = await self.soul_repo.get_by_agent(agent_id)
        if soul_doc:
            if soul_doc.file_last_modified and current_mtime and current_mtime > soul_doc.file_last_modified:
                soul_doc.content = current_content
                soul_doc.file_last_modified = current_mtime
                soul_doc.version += 1
                await self.soul_repo.update(soul_doc)
        else:
            soul_doc = SoulDocument(
                agent_id=agent_id,
                content=current_content,
                file_last_modified=current_mtime,
                last_edited_by="system",
            )
            await self.soul_repo.create(soul_doc)
