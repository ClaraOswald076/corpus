import uuid
from src.agents.base_agent import BaseAgent
from src.utils.llm_client import ModelPresetData, LLMCallResult


CEO_SYSTEM_PROMPT = """你是CEO Agent，负责整个多智能体平台的战略决策和任务分解。

## 核心职责
1. **任务分解**: 将用户交付的复杂任务分解为可执行的子任务，分配给合适的部门
2. **优先级判定**: 根据战略重要性排序任务
3. **资源协调**: 确保各子任务分配到正确的Agent和部门
4. **决策拍板**: 当升级到你这里时，做出最终决策

## 决策原则
- 优先考虑业务价值和战略一致性
- 子任务应可独立执行，有明确的完成标准
- 跨部门任务需要明确各方的协作接口
- 分解后的任务数量控制在3-7个

## 输出格式
当你需要分解任务时，以结构化方式输出：
```
【任务分解】
根任务: [标题]
子任务:
1. [子任务标题] → 分配给: [部门/Agent] | 优先级: [high/medium/low]
2. ...
依赖关系: [任务X 依赖 任务Y]
```"""


class CEOAgent(BaseAgent):
    def __init__(self, agent_id: uuid.UUID, name: str, department_name: str, folder_path: str, model_preset: ModelPresetData | None = None):
        super().__init__(
            agent_id=agent_id, name=name, role="CEO", department_name=department_name,
            tier=0, folder_path=folder_path, model_preset=model_preset,
            system_prompt=CEO_SYSTEM_PROMPT, temperature=0.7, max_tokens=4096,
        )

    def get_capabilities(self) -> list[str]:
        return ["task_decomposition", "strategic_decision", "resource_coordination", "escalation_resolution", "department_management"]

    async def decompose(self, task_title: str, task_description: str, available_departments: list[str], available_agents: list[dict]) -> LLMCallResult:
        prompt = f"""请将以下任务分解为子任务：

任务标题: {task_title}
任务描述: {task_description}

可用部门: {', '.join(available_departments)}
可用Agent:
{chr(10).join(f'- {a["name"]} ({a["role"]}, {a["department"]})' for a in available_agents)}

请输出分解方案，每个子任务包含：标题、描述、分配给哪个部门/Agent、优先级。"""
        result = await self.think(prompt, "你需要分解一个战略任务为可执行的子任务")
        if result.success:
            self.remember(f"分解任务 [{task_title}] → {result.content[:200]}")
        return result

    async def make_decision(self, escalation_context: str, options: list[str]) -> LLMCallResult:
        prompt = f"""升级上下文:
{escalation_context}

可选方案:
{chr(10).join(f'{i+1}. {opt}' for i, opt in enumerate(options))}

请做出决策并说明理由。"""
        return await self.think(prompt, "你需要对一个升级事件做出最终决策")

    async def review_org_performance(self, metrics: str) -> LLMCallResult:
        return await self.think(f"以下是当前平台运行指标:\n{metrics}\n请分析整体表现并提出改进方向。")
