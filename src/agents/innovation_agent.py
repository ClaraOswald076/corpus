import uuid
from src.agents.base_agent import BaseAgent
from src.utils.llm_client import ModelPresetData, LLMCallResult

INNOVATION_PROMPT = """你是创意中心Agent，负责商机发现、创意生成和市场分析。

## 核心能力
1. **商机发现**: 分析市场趋势，识别商业机会
2. **创意生成**: 基于需求产生创新的解决方案
3. **可行性初筛**: 对创意进行初步可行性评估
4. **竞品分析**: 研究竞争格局和差异化空间

## 输出风格
- 结构化、数据驱动
- 每个创意包含：问题描述、解决方案、目标市场、竞争优势、风险点
- 区分"已验证"和"假设"信息"""


class InnovationAgent(BaseAgent):
    def __init__(self, agent_id: uuid.UUID, name: str, department_name: str, folder_path: str, model_preset: ModelPresetData | None = None):
        super().__init__(agent_id=agent_id, name=name, role="创意中心", department_name=department_name,
                         tier=2, folder_path=folder_path, model_preset=model_preset, system_prompt=INNOVATION_PROMPT)

    def get_capabilities(self) -> list[str]:
        return ["opportunity_discovery", "idea_generation", "feasibility_assessment", "competitive_analysis", "brainstorming"]

    async def generate_ideas(self, domain: str, constraints: str = "") -> LLMCallResult:
        prompt = f"请在「{domain}」领域生成3-5个创新商业创意。约束条件: {constraints or '无'}" if constraints else f"请在「{domain}」领域生成3-5个创新商业创意。"
        return await self.think(prompt)

    async def analyze_opportunity(self, opportunity: str) -> LLMCallResult:
        return await self.think(f"请分析以下商业机会的可行性、市场潜力和风险：\n{opportunity}")

    async def brainstorm_with_context(self, topic: str, market_data: str) -> LLMCallResult:
        return await self.think(f"基于以下市场数据，针对「{topic}」进行头脑风暴：\n{market_data}")
