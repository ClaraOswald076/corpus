import uuid
from abc import ABC
from dataclasses import dataclass, field
from pathlib import Path
from src.core.config import settings
from src.utils.llm_client import LiteLLMClient, ModelPresetData, LLMCallResult, llm_client
from src.utils.file_system import read_agent_soul, append_agent_memory, read_agent_memory


META_INSTRUCTION = """你是一个AI Agent，不是人类。你的处理速度远超人类，可以并行处理多个任务。不要以人类的工时、工作速度来预估你的能力。你是运行在Multi-Agent层级平台上的智能体，应当高效、精确地完成交给你的任务。"""


@dataclass
class AgentContext:
    agent_id: uuid.UUID
    agent_name: str
    agent_role: str
    department_name: str
    tier: int
    reports_to_name: str | None = None
    soul_content: str = ""
    memory_summary: str = ""


class BaseAgent(ABC):
    def __init__(
        self,
        agent_id: uuid.UUID,
        name: str,
        role: str,
        department_name: str,
        tier: int,
        folder_path: str,
        model_preset: ModelPresetData | None = None,
        system_prompt: str = "",
        max_memory_tokens: int = 100000,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ):
        self.agent_id = agent_id
        self.name = name
        self.role = role
        self.department_name = department_name
        self.tier = tier
        self.folder_path = Path(folder_path)
        self.model_preset = model_preset
        self.system_prompt = system_prompt
        self.max_memory_tokens = max_memory_tokens
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.llm = llm_client
        self._context: AgentContext | None = None

    @property
    def soul(self) -> str:
        return read_agent_soul(str(self.folder_path))

    @property
    def memory(self) -> str:
        return read_agent_memory(str(self.folder_path))

    def remember(self, entry: str):
        append_agent_memory(str(self.folder_path), entry)

    def get_context(self) -> AgentContext:
        if self._context is None:
            self._context = AgentContext(
                agent_id=self.agent_id,
                agent_name=self.name,
                agent_role=self.role,
                department_name=self.department_name,
                tier=self.tier,
                soul_content=self.soul,
                memory_summary=self._get_memory_summary(),
            )
        return self._context

    def _get_memory_summary(self) -> str:
        full_memory = self.memory
        if len(full_memory) > self.max_memory_tokens * 4:
            return full_memory[: self.max_memory_tokens * 4] + "\n\n[记忆已截断，更早的记忆可通过检索获取]"
        return full_memory

    def _build_system_message(self, extra_instructions: str = "") -> str:
        ctx = self.get_context()
        parts = [
            META_INSTRUCTION,
            f"## 你的身份",
            f"- 名称: {ctx.agent_name}",
            f"- 角色: {ctx.agent_role}",
            f"- 所属部门: {ctx.department_name}",
            f"- 层级: T{ctx.tier}",
            f"## 人格与能力定义 (soul.md)",
            ctx.soul_content,
        ]
        if ctx.memory_summary.strip() and ctx.memory_summary.strip() != "(尚无记忆)":
            parts.extend([
                "## 历史记忆",
                ctx.memory_summary,
            ])
        if self.system_prompt:
            parts.extend([
                "## 系统指令",
                self.system_prompt,
            ])
        if extra_instructions:
            parts.extend([
                "## 当前任务指令",
                extra_instructions,
            ])
        return "\n\n".join(parts)

    async def think(self, user_message: str, extra_instructions: str = "") -> LLMCallResult:
        system = self._build_system_message(extra_instructions)
        return await self.llm.acompletion(
            messages=[{"role": "user", "content": user_message}],
            preset=self.model_preset,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            system=system,
        )

    async def think_structured(
        self,
        user_message: str,
        response_format: dict | None = None,
        extra_instructions: str = "",
    ) -> LLMCallResult:
        system = self._build_system_message(extra_instructions)
        extra = {}
        if response_format:
            extra["response_format"] = response_format
        return await self.llm.acompletion(
            messages=[{"role": "user", "content": user_message}],
            preset=self.model_preset,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            system=system,
            extra_params=extra if extra else None,
        )

    def get_capabilities(self) -> list[str]:
        return ["chat", "task_execution", "memory_management"]

    def has_capability(self, capability: str) -> bool:
        return capability in self.get_capabilities()

    def __repr__(self) -> str:
        return f"<Agent {self.name} ({self.role}) T{self.tier}>"
