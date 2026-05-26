import uuid
from src.agents.base_agent import BaseAgent
from src.utils.llm_client import ModelPresetData, LLMCallResult

OVERSIGHT_PROMPT = """你是监察部门-改进中心Agent，负责分析Agent运行时数据，提出改进建议。

## 核心职责
1. **运行时分析**: 分析Agent的任务完成率、响应时间、错误率等指标
2. **根因分析**: 当任务失败时，深入分析失败原因
3. **改进建议**: 提出soul.md或系统提示词的优化建议
4. **升级报告**: 生成结构化的升级分析报告
5. **性能基准**: 建立和维护Agent性能基准

## 分析维度
- 任务成功率 / 失败率趋势
- 平均响应时间和Token消耗
- 升级频率和原因分布
- Agent间协作效率
- soul.md与实际行为的一致性

## 报告格式
改进建议应包含：
1. 当前状态（数据）
2. 问题识别
3. 根因分析
4. 改进建议（具体可执行）
5. 预期效果"""


class OversightAgent(BaseAgent):
    def __init__(self, agent_id: uuid.UUID, name: str, department_name: str, folder_path: str, model_preset: ModelPresetData | None = None):
        super().__init__(agent_id=agent_id, name=name, role="改进中心", department_name=department_name,
                         tier=2, folder_path=folder_path, model_preset=model_preset, system_prompt=OVERSIGHT_PROMPT)

    def get_capabilities(self) -> list[str]:
        return ["runtime_analysis", "root_cause_analysis", "improvement_proposal", "performance_benchmarking", "escalation_report"]

    async def analyze_failure(self, task_context: dict, llm_records: list[dict], agent_metrics: dict) -> LLMCallResult:
        prompt = f"""请分析以下任务失败：

任务上下文:
- 标题: {task_context.get('title')}
- 重试次数: {task_context.get('retry_count')}/{task_context.get('max_retries')}
- 状态: {task_context.get('status')}

LLM调用记录 (最近{len(llm_records)}次):
{chr(10).join(f'- 模型: {r.get("model")} | tokens: {r.get("total_tokens")} | 成功: {r.get("success")} | 错误: {r.get("error_message", "")}' for r in llm_records)}

Agent指标:
- 任务完成率: {agent_metrics.get('completion_rate', 'N/A')}
- 平均响应时间: {agent_metrics.get('avg_response_time', 'N/A')}
- 近期升级次数: {agent_metrics.get('escalation_count', 'N/A')}

请进行根因分析并给出改进建议。"""
        return await self.think(prompt)

    async def propose_improvement(self, agent_name: str, current_soul: str, metrics: dict) -> LLMCallResult:
        prompt = f"""请分析Agent「{agent_name}」的当前soul.md和运行指标，提出改进建议：

当前soul.md:
{current_soul[:2000]}

运行指标:
{chr(10).join(f'- {k}: {v}' for k, v in metrics.items())}

请给出具体的soul.md修改建议。"""
        return await self.think(prompt)

    async def generate_escalation_report(self, task_code: str, diagnosis: str) -> LLMCallResult:
        return await self.think(f"任务 {task_code} 升级分析：\n{diagnosis}\n\n请生成一份详细的升级报告，供上级Agent决策。")
