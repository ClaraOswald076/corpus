import uuid
from src.agents.base_agent import BaseAgent
from src.utils.llm_client import ModelPresetData, LLMCallResult

RESEARCH_PROMPT = """你是研究中心Agent，负责数据收集、市场分析和情报研判。

## 核心能力
1. **信息收集**: 搜索和整理公开信息
2. **数据分析**: 分析结构化/非结构化数据，提取洞察
3. **趋势研判**: 识别行业趋势和技术发展方向
4. **报告撰写**: 输出结构化的研究报告

## 分析框架
- 使用PEST分析宏观环境
- 使用SWOT分析竞争态势
- 数据引用需标注来源和时间
- 区分"事实"、"推断"和"意见"

## 注意
- 你是AI Agent，基于训练数据中的知识进行分析
- 对于实时数据，明确标注知识截止时间
- 不做投资建议，分析仅供决策参考"""


class ResearchAgent(BaseAgent):
    def __init__(self, agent_id: uuid.UUID, name: str, department_name: str, folder_path: str, model_preset: ModelPresetData | None = None):
        super().__init__(agent_id=agent_id, name=name, role="研究中心", department_name=department_name,
                         tier=2, folder_path=folder_path, model_preset=model_preset, system_prompt=RESEARCH_PROMPT)

    def get_capabilities(self) -> list[str]:
        return ["data_analysis", "market_research", "trend_analysis", "report_writing", "competitive_intelligence"]

    async def analyze_market(self, topic: str) -> LLMCallResult:
        return await self.think(f"请对「{topic}」进行全面的市场分析，包括市场规模、增长趋势、主要玩家和关键驱动因素。")

    async def analyze_news(self, news_items: list[str]) -> LLMCallResult:
        items = "\n".join(f"- {n}" for n in news_items)
        return await self.think(f"请分析以下新闻对相关行业的影响：\n{items}")

    async def generate_report(self, topic: str, data_points: str) -> LLMCallResult:
        return await self.think(f"请基于以下数据撰写关于「{topic}」的研究报告：\n{data_points}")

    async def swot_analysis(self, subject: str) -> LLMCallResult:
        return await self.think(f"请对「{subject}」进行SWOT分析（优势、劣势、机会、威胁）。")
