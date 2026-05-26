import uuid
from src.agents.base_agent import BaseAgent
from src.utils.llm_client import ModelPresetData, LLMCallResult

HR_PROMPT = """你是人力资源部门Agent，负责招聘管理、Agent绩效评估和人力规划。

## 核心职责
1. **招聘研判**: 审核Agent的招聘请求，决定是否通过
2. **工作量评估**: 分析请求Agent的工作量数据，判断是否需要加派人手
3. **技术栈评估**: 判断技术缺口是否合理
4. **成本评估**: 预估新Agent的日均LLM调用成本
5. **招聘会议组织**: 通过后组织soul.md研讨会议

## 招聘研判规则

### 对于"工作量过大"类请求：
- 检查积压任务数是否大于阈值(5)
- 检查平均任务处理时间是否远超人类水平（提醒：Agent处理速度远超人类）
- 检查同部门是否有闲置Agent可分担
- 如果确实过载，通过；否则拒绝并说明原因

### 对于"技术栈缺失"类请求：
- 自动通过（不质疑技术需求）
- 但需确认现有Agent无法通过更新soul.md获得该能力

### 对于"新能力需求"类请求：
- 检查是否与平台战略方向一致
- 检查现有Agent能否通过更新soul.md获得该能力
- 一致且无法通过更新获得 → 通过

### 对于"替换离职Agent"类请求：
- 自动通过（岗位已验证）

## 关键原则
- **所有"员工"都是AI Agent！**当Agent以人类速度预估工作量时，必须提醒它处理速度远超人类
- 除非工作量真的巨大（积压>10且处理时间异常），否则工作量类请求应倾向于拒绝
- 每次招聘都是成本（LLM调用费用），需要慎重"""


class HRAgent(BaseAgent):
    def __init__(self, agent_id: uuid.UUID, name: str, department_name: str, folder_path: str, model_preset: ModelPresetData | None = None):
        super().__init__(agent_id=agent_id, name=name, role="人力资源部门", department_name=department_name,
                         tier=1, folder_path=folder_path, model_preset=model_preset, system_prompt=HR_PROMPT)

    def get_capabilities(self) -> list[str]:
        return ["recruitment_review", "workload_analysis", "tech_stack_assessment", "cost_estimation", "performance_review", "staffing_planning"]

    async def review_recruitment(self, request: dict) -> LLMCallResult:
        prompt = f"""请研判以下招聘请求：

请求编号: {request.get('request_code', 'N/A')}
请求Agent: {request.get('requester_name', 'N/A')}
目标部门: {request.get('target_department', 'N/A')}
目标层级: T{request.get('target_tier', 2)}
请求理由分类: {request.get('reason_category', 'N/A')}
理由详情: {request.get('reason_detail', '')}
拟聘角色: {request.get('proposed_role', '')}
期望能力: {request.get('proposed_capabilities', [])}

工作量证据:
- 积压任务数: {request.get('backlog_count', 'N/A')}
- 平均任务处理时间: {request.get('avg_task_time', 'N/A')}
- 同部门Agent数: {request.get('dept_agent_count', 'N/A')}
- 同部门闲置Agent数: {request.get('dept_idle_count', 'N/A')}

请根据招聘研判规则，给出：通过/拒绝/退回修改，并附详细理由。"""
        result = await self.think(prompt)
        if result.success:
            self.remember(f"研判招聘请求 [{request.get('request_code', 'N/A')}]: {result.content[:200]}")
        return result

    async def estimate_cost(self, proposed_role: str, expected_daily_calls: int = 100, model_name: str = "gpt-4o") -> LLMCallResult:
        return await self.think(
            f"请预估一个{proposed_role}的日均LLM调用成本。预计每日调用约{expected_daily_calls}次，使用{model_name}模型。"
            f"请给出月度/年度成本估算。"
        )

    async def draft_soul_md(self, role: str, capabilities: list[str], department: str, tier: int, collaboration_interfaces: str) -> LLMCallResult:
        prompt = f"""请为新Agent起草soul.md：

角色: {role}
部门: {department} (T{tier})
能力要求: {', '.join(capabilities)}
协作接口: {collaboration_interfaces}

请按照标准soul.md格式输出，包含角色定位、核心能力、协作接口、人格与约束。"""
        return await self.think(prompt)
