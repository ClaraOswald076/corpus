import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from src.api.deps import get_db
from src.services.model_preset import ModelPresetService
from src.agents.base_agent import BaseAgent
from src.utils.llm_client import ModelPresetData
from src.core.config import settings

router = APIRouter()


async def _auto_create_tasks_from_message(db, message: str, speaker) -> str:
    import re
    from src.services.task_manager import TaskManagerService, TaskCreate, TaskPriority
    from src.repositories.agent_repo import AgentRepository
    from src.repositories.organization_repo import DepartmentRepository

    svc = TaskManagerService(db)
    agent_repo = AgentRepository(db)
    dept_repo = DepartmentRepository(db)
    created = []

    # Pattern 1: `[任务分派]` → 发送至：**Agent名**
    pattern1 = re.findall(r'\[任务分派\][\s\S]*?发送至[：:]\s*\*{0,2}(.+?)\*{0,2}', message)
    if pattern1:
        for target_name in pattern1:
            target_name = target_name.strip()
            target_agent = await agent_repo.get_by_name(target_name)
            if not target_agent:
                # Try department
                dept = await dept_repo.get_by_name(target_name)
                if dept:
                    agents = await agent_repo.list_by_department(dept.id)
                    target_agent = agents[0] if agents else None

            # Extract title and content
            title_match = re.search(r'(?:启动|执行)\s*[「「](.+?)[」」]', message)
            content_match = re.search(r'\[内容\][\s\S]*?(?=\[|`\[)', message)

            title = title_match.group(1).strip() if title_match else f"任务: {target_name}"
            description = content_match.group(0).strip() if content_match else message[:1000]

            task = await svc.create_task(TaskCreate(
                title=title,
                description=description,
                created_by=speaker.name,
                priority=TaskPriority.HIGH,
                assigned_agent_id=target_agent.id if target_agent else None,
                assigned_department_id=dept.id if (not target_agent and dept) else None,
                tags=["CEO指派"],
            ))
            created.append(f"[{task.task_code}] {title} → {target_name}")
            await db.flush()

    # Pattern 2: `[公开通知]` — just log it
    notify = re.findall(r'\[公开通知\]', message)
    if notify:
        created.append("📢 公开通知已记录")

    if created:
        return "✅ **已自动创建任务:**\n" + "\n".join(f"- {c}" for c in created)
    return ""



class ChatRequest(BaseModel):
    agent_name: str
    message: str


class ChatResponse(BaseModel):
    agent_name: str
    agent_role: str
    reply: str
    tokens_used: int = 0
    cost_usd: float = 0.0


@router.post("/", response_model=ChatResponse)
async def chat_with_agent(data: ChatRequest, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from src.models.organization import Agent as AgentModel
    from src.models.agent import ModelPreset

    result = await db.execute(
        select(AgentModel).options(
            selectinload(AgentModel.department),
            selectinload(AgentModel.model_preset).selectinload(ModelPreset.api_keys),
        ).where(AgentModel.name == data.agent_name)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{data.agent_name}' 不存在")
    if not agent.is_active:
        raise HTTPException(status_code=400, detail=f"Agent '{data.agent_name}' 已停用")

    dept_name = agent.department.name if agent.department else "未知部门"
    dept_tier = agent.department.tier if agent.department else 2

    # Build model preset from eagerly loaded data
    model_preset = None
    mp = agent.model_preset
    if mp and mp.is_active:
        from src.utils.security import decrypt_api_key
        api_key = ""
        if mp.api_keys:
            active_keys = [k for k in mp.api_keys if k.is_active]
            if active_keys:
                try:
                    api_key = decrypt_api_key(active_keys[0].encrypted_key)
                except Exception:
                    pass
        model_preset = ModelPresetData(
            name=mp.name,
            litellm_model_string=mp.litellm_model_string,
            default_params=mp.default_params or {},
            api_key=api_key,
        )

    if not model_preset:
        raise HTTPException(
            status_code=400,
            detail=f"Agent '{data.agent_name}' 未配置模型预设。请先在'模型预设'页签中创建预设，再为其分配模型。"
        )

    folder_path = str(settings.project_root / agent.agent_folder_path)
    bot = BaseAgent(
        agent_id=agent.id,
        name=agent.name,
        role=agent.role,
        department_name=dept_name,
        tier=dept_tier,
        folder_path=folder_path,
        model_preset=model_preset,
        system_prompt=agent.system_prompt or "",
        max_memory_tokens=agent.max_memory_tokens,
        temperature=agent.temperature,
        max_tokens=agent.max_tokens,
    )

    # Auto-detect task assignments and create them
    task_created_msg = ""
    if agent.name in ("CEO", "产品部负责人", "人力部负责人") and ("任务分派" in data.message or "任务：**" in data.message or "【任务" in data.message or "`[任务分派]`" in data.message):
        task_created_msg = await _auto_create_tasks_from_message(db, data.message, agent)

    extra = f"\n\n[系统提示：用户发送了任务分派指令。请确认收到任务并说明执行计划。]" if task_created_msg else ""
    full_message = data.message + extra

    result = await bot.think(full_message)
    if not result.success:
        raise HTTPException(status_code=500, detail=f"LLM调用失败: {result.error_message}")

    bot.remember(f"[对话] 用户: {data.message[:200]}\n回复: {result.content[:200]}")

    reply = result.content
    if task_created_msg:
        reply = task_created_msg + "\n\n---\n\n" + reply

    return ChatResponse(
        agent_name=agent.name,
        agent_role=agent.role,
        reply=reply,
        tokens_used=result.total_tokens,
        cost_usd=result.estimated_cost_usd,
    )


@router.get("/agents")
async def list_chatable_agents(db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from src.models.organization import Agent as AgentModel
    result = await db.execute(
        select(AgentModel).options(selectinload(AgentModel.department), selectinload(AgentModel.model_preset)).where(AgentModel.is_active == True)
    )
    agents = result.scalars().all()
    return [
        {
            "name": a.name,
            "role": a.role,
            "department": a.department.name if a.department else "未知",
            "tier": a.department.tier if a.department else None,
            "has_model": a.model_preset_id is not None,
            "is_active": a.is_active,
        }
        for a in agents
    ]
