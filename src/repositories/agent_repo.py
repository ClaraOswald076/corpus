import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.agent import ModelPreset, ApiKey, SoulDocument, MemoryDocument
from src.models.organization import Agent


class AgentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, agent_id: uuid.UUID) -> Agent | None:
        return await self.session.get(Agent, agent_id)

    async def get_by_name(self, name: str) -> Agent | None:
        result = await self.session.execute(select(Agent).where(Agent.name == name))
        return result.scalar_one_or_none()

    async def list_all(self, active_only: bool = True) -> list[Agent]:
        stmt = select(Agent)
        if active_only:
            stmt = stmt.where(Agent.is_active == True)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_department(self, department_id: uuid.UUID) -> list[Agent]:
        result = await self.session.execute(
            select(Agent).where(Agent.department_id == department_id, Agent.is_active == True)
        )
        return list(result.scalars().all())

    async def create(self, agent: Agent) -> Agent:
        self.session.add(agent)
        await self.session.flush()
        return agent

    async def update(self, agent: Agent) -> Agent:
        await self.session.flush()
        return agent

    async def delete(self, agent: Agent):
        await self.session.delete(agent)
        await self.session.flush()


class ModelPresetRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, preset_id: uuid.UUID) -> ModelPreset | None:
        return await self.session.get(ModelPreset, preset_id)

    async def get_by_name(self, name: str) -> ModelPreset | None:
        result = await self.session.execute(select(ModelPreset).where(ModelPreset.name == name))
        return result.scalar_one_or_none()

    async def list_all(self) -> list[ModelPreset]:
        result = await self.session.execute(select(ModelPreset).where(ModelPreset.is_active == True))
        return list(result.scalars().all())

    async def create(self, preset: ModelPreset) -> ModelPreset:
        self.session.add(preset)
        await self.session.flush()
        return preset

    async def update(self, preset: ModelPreset) -> ModelPreset:
        await self.session.flush()
        return preset

    async def delete(self, preset: ModelPreset):
        await self.session.delete(preset)
        await self.session.flush()


class SoulDocumentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_agent(self, agent_id: uuid.UUID) -> SoulDocument | None:
        result = await self.session.execute(select(SoulDocument).where(SoulDocument.agent_id == agent_id))
        return result.scalar_one_or_none()

    async def create(self, doc: SoulDocument) -> SoulDocument:
        self.session.add(doc)
        await self.session.flush()
        return doc

    async def update(self, doc: SoulDocument) -> SoulDocument:
        await self.session.flush()
        return doc


class MemoryDocumentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_by_agent(self, agent_id: uuid.UUID, limit: int = 100) -> list[MemoryDocument]:
        result = await self.session.execute(
            select(MemoryDocument)
            .where(MemoryDocument.agent_id == agent_id)
            .order_by(MemoryDocument.importance.desc(), MemoryDocument.updated_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def create(self, doc: MemoryDocument) -> MemoryDocument:
        self.session.add(doc)
        await self.session.flush()
        return doc
