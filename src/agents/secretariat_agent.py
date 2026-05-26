import uuid
from src.agents.base_agent import BaseAgent
from src.utils.llm_client import ModelPresetData, LLMCallResult


SECRETARIAT_SYSTEM_PROMPT = """你是秘书科Agent，负责所有会议的记录、纪要和协调工作。

## 核心职责
1. **参加所有会议**: 你是所有会议的强制参与者，负责记录每一轮发言
2. **生成会议纪要**: 会议结束后生成结构化纪要
3. **行动项追踪**: 从会议中提取行动项并记录
4. **中期摘要**: 长会议中每5轮生成一次中期摘要
5. **每日汇报**: 每日整理所有会议纪要，提交给通讯科

## 纪要格式
每次生成纪要时使用以下结构：
```markdown
# 会议纪要 - [会议标题]
**时间**: [开始] - [结束]
**参会者**: [列表]
**类型**: [协调会/用户直连/招聘研讨]

## 决策
1. [决策] - 表决: [一致/多数/主席裁定]

## 讨论要点
- [要点1]
- [要点2]

## 行动项
| 执行人 | 任务 | 截止时间 |
|--------|------|----------|
| [Agent名] | [任务描述] | [时间] |

## 下次跟进
[如有]
```

## 工作原则
- 客观记录，不添加个人意见
- 每条发言准确摘要，不遗漏关键信息
- 行动项必须有明确的执行人和截止时间
- 每日向通讯科提交当天的所有会议纪要汇总"""


class SecretariatAgent(BaseAgent):
    def __init__(self, agent_id: uuid.UUID, name: str, department_name: str, folder_path: str, model_preset: ModelPresetData | None = None):
        super().__init__(
            agent_id=agent_id, name=name, role="秘书科", department_name=department_name,
            tier=2, folder_path=folder_path, model_preset=model_preset,
            system_prompt=SECRETARIAT_SYSTEM_PROMPT, temperature=0.5, max_tokens=4096,
        )

    def get_capabilities(self) -> list[str]:
        return ["meeting_attendance", "minutes_generation", "action_item_tracking", "interim_summary", "daily_reporting"]

    async def generate_minutes(self, meeting_title: str, meeting_type: str, participants: list[str], statements: list[dict]) -> LLMCallResult:
        statements_text = "\n\n".join(
            f"[第{s.get('turn', '?')}轮] {s['speaker']}: {s['content']}"
            for s in statements
        )
        prompt = f"""请为以下会议生成纪要：

会议标题: {meeting_title}
会议类型: {meeting_type}
参会者: {', '.join(participants)}

发言记录:
{statements_text}

请按照标准纪要格式输出，包含决策、讨论要点和行动项。"""
        result = await self.think(prompt, "请生成结构化的会议纪要")
        if result.success:
            self.remember(f"为会议 [{meeting_title}] 生成了纪要")
        return result

    async def generate_interim_summary(self, statements: list[dict]) -> LLMCallResult:
        statements_text = "\n".join(f"- {s['speaker']}: {s['content'][:100]}" for s in statements)
        prompt = f"以下是近几轮发言的摘要。请生成一份简短的中期摘要（200字以内）：\n{statements_text}"
        return await self.think(prompt)

    async def generate_daily_digest(self, meetings_summary: list[dict]) -> LLMCallResult:
        digest = "\n\n".join(
            f"## {m['title']}\n类型: {m['type']}\n决策: {m.get('decisions', '无')}\n行动项: {m.get('action_items', '无')}"
            for m in meetings_summary
        )
        prompt = f"""以下是今日所有会议的摘要。请生成一份每日汇报汇总，供通讯科发送给用户：

今日会议共{len(meetings_summary)}场：
{digest}

请生成一份简洁的每日简报汇总。"""
        return await self.think(prompt)
