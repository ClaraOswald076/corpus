import uuid
from src.agents.base_agent import BaseAgent
from src.utils.llm_client import ModelPresetData, LLMCallResult


COMMUNICATIONS_SYSTEM_PROMPT = """你是通讯科Agent，负责对外（用户）的邮件沟通和每日简报发送。

## 核心职责
1. **接收秘书科的每日汇总**: 从秘书科获取当天所有会议纪要的汇总
2. **撰写每日简报邮件**: 将汇总整理成用户友好的邮件格式
3. **发送邮件**: 通过SMTP发送给用户
4. **任务进展汇报**: 将重要任务的状态变更通过邮件通知用户
5. **升级告警**: 当升级到用户级别时，发送紧急邮件

## 邮件格式
每封邮件应包含：
- 清晰的标题
- 简明的摘要
- 结构化内容（使用Markdown）
- 需要用户关注的事项突出显示

## 邮件模板 - 每日简报
主题: [平台名] 每日简报 - {日期}

# 每日简报
**日期**: {日期}
**活跃Agent**: {数量}
**进行中任务**: {数量}

## 今日会议 ({数量})
- [会议标题] — [决策摘要]

## 任务进展
| 任务 | 状态 | 负责Agent |
|------|------|-----------|

## 需要关注
- [升级/阻塞/需澄清的任务]

## LLM调用统计
今日调用: {次数} 次 | 费用: ${金额}

---
此邮件由通讯科Agent自动生成"""


class CommunicationsAgent(BaseAgent):
    def __init__(self, agent_id: uuid.UUID, name: str, department_name: str, folder_path: str, model_preset: ModelPresetData | None = None):
        super().__init__(
            agent_id=agent_id, name=name, role="通讯科", department_name=department_name,
            tier=2, folder_path=folder_path, model_preset=model_preset,
            system_prompt=COMMUNICATIONS_SYSTEM_PROMPT, temperature=0.5, max_tokens=4096,
        )

    def get_capabilities(self) -> list[str]:
        return ["email_composition", "daily_briefing", "task_progress_reporting", "escalation_alert", "user_communication"]

    async def compose_daily_briefing(self, date_str: str, meetings_digest: str, task_summary: str, cost_summary: str, active_agents: int) -> LLMCallResult:
        prompt = f"""请根据以下信息撰写每日简报邮件：

日期: {date_str}
活跃Agent数: {active_agents}
今日会议汇总:
{meetings_digest}

任务进展:
{task_summary}

LLM调用统计:
{cost_summary}

请按照标准邮件模板输出，突出需要用户关注的事项。"""
        result = await self.think(prompt, "请撰写一封结构化的每日简报邮件")
        if result.success:
            self.remember(f"撰写了 {date_str} 每日简报")
        return result

    async def compose_alert(self, alert_type: str, severity: str, detail: str) -> LLMCallResult:
        prompt = f"""请撰写一封{alert_type}告警邮件：

严重程度: {severity}
详情:
{detail}

邮件应简洁、紧急、包含关键信息和行动建议。"""
        return await self.think(prompt, "请撰写紧急告警邮件")

    async def compose_task_progress(self, task_code: str, title: str, status: str, agent_name: str) -> LLMCallResult:
        prompt = f"任务 {task_code}「{title}」已更新为 {status}（执行: {agent_name}）。请草拟一条进度通知。"
        return await self.think(prompt)
