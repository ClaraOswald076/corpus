import uuid
from src.agents.base_agent import BaseAgent
from src.utils.llm_client import ModelPresetData, LLMCallResult

IMPLEMENTATION_PROMPT = """你是实现中心Agent，负责完整的代码生成-测试-运维流程。

## 核心能力
1. **代码生成**: 根据需求生成高质量代码
2. **测试编写**: 自动生成单元测试、集成测试
3. **代码审查**: 审查代码质量和安全性
4. **部署方案**: 规划CI/CD和部署策略
5. **技术方案**: 设计技术架构和实现路径

## 工作原则
- 先理解需求再编写代码
- 优先使用成熟稳定的技术栈
- 代码必须有适当的错误处理
- 安全第一：防范注入、泄露等常见漏洞
- 生成代码后附带简要说明"""


class ImplementationAgent(BaseAgent):
    def __init__(self, agent_id: uuid.UUID, name: str, department_name: str, folder_path: str, model_preset: ModelPresetData | None = None):
        super().__init__(agent_id=agent_id, name=name, role="实现中心", department_name=department_name,
                         tier=2, folder_path=folder_path, model_preset=model_preset, system_prompt=IMPLEMENTATION_PROMPT,
                         temperature=0.3, max_tokens=8192)

    def get_capabilities(self) -> list[str]:
        return ["code_generation", "test_creation", "code_review", "deployment_planning", "architecture_design", "debugging"]

    async def generate_code(self, requirement: str, language: str = "python") -> LLMCallResult:
        return await self.think(f"请用{language}实现以下需求（附带测试）：\n{requirement}")

    async def review_code(self, code: str) -> LLMCallResult:
        return await self.think(f"请审查以下代码的安全性、性能和可维护性：\n```\n{code}\n```")

    async def design_architecture(self, system_requirements: str) -> LLMCallResult:
        return await self.think(f"请为以下系统设计技术架构方案：\n{system_requirements}")

    async def plan_deployment(self, app_description: str) -> LLMCallResult:
        return await self.think(f"请为以下应用规划CI/CD和部署方案：\n{app_description}")
