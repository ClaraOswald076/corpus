import uuid
from dataclasses import dataclass, field
from typing import Protocol
from src.agents.base_agent import BaseAgent


@dataclass
class AgentMetadata:
    agent_id: uuid.UUID
    name: str
    role: str
    department_name: str
    tier: int
    capabilities: list[str]
    model_preset_name: str | None = None
    is_active: bool = True
    availability_status: str = "available"


class AgentRegistry:
    def __init__(self):
        self._agents: dict[uuid.UUID, BaseAgent] = {}
        self._metadata: dict[uuid.UUID, AgentMetadata] = {}

    def register(self, agent: BaseAgent, metadata: AgentMetadata):
        self._agents[agent.agent_id] = agent
        self._metadata[agent.agent_id] = metadata

    def unregister(self, agent_id: uuid.UUID):
        self._agents.pop(agent_id, None)
        self._metadata.pop(agent_id, None)

    def get_agent(self, agent_id: uuid.UUID) -> BaseAgent | None:
        return self._agents.get(agent_id)

    def get_metadata(self, agent_id: uuid.UUID) -> AgentMetadata | None:
        return self._metadata.get(agent_id)

    def find_by_capability(self, capability: str) -> list[AgentMetadata]:
        return [m for m in self._metadata.values() if capability in m.capabilities]

    def find_by_department(self, department_name: str) -> list[AgentMetadata]:
        return [m for m in self._metadata.values() if m.department_name == department_name]

    def find_by_tier(self, tier: int) -> list[AgentMetadata]:
        return [m for m in self._metadata.values() if m.tier == tier]

    def find_active(self) -> list[AgentMetadata]:
        return [m for m in self._metadata.values() if m.is_active and m.availability_status == "available"]

    def update_availability(self, agent_id: uuid.UUID, status: str):
        if agent_id in self._metadata:
            self._metadata[agent_id].availability_status = status

    def list_all(self) -> list[AgentMetadata]:
        return list(self._metadata.values())

    @property
    def agent_count(self) -> int:
        return len(self._agents)


agent_registry = AgentRegistry()
