import asyncio
import uuid
import typer
from src.core.database import init_db

app = typer.Typer(name="ma", help="多智能体层级平台 CLI")

# ─── 数据库 ──────────────────────────────────────────

@app.command()
def init():
    """初始化数据库和默认组织架构"""
    from src.cli.seed import seed_default_org
    asyncio.run(seed_default_org())


@app.command()
def seed_agents(preset_name: str = typer.Option("", help="模型预设名称(可选)")):
    """创建所有部门的默认Agent员工"""
    from src.cli.seed_agents import seed_agents as _seed
    asyncio.run(_seed(preset_name))


@app.command()
def db_init():
    """仅初始化数据库表（不含种子数据）"""
    asyncio.run(init_db())
    typer.echo("[OK] 数据库表已创建")


# ─── 模型预设 ──────────────────────────────────────────

@app.command()
def preset_list():
    """列出所有模型预设"""
    async def _list():
        from src.core.database import async_session_factory
        from src.repositories.agent_repo import ModelPresetRepository
        async with async_session_factory() as session:
            repo = ModelPresetRepository(session)
            presets = await repo.list_all()
            if not presets:
                typer.echo("(无模型预设，请先创建)")
                return
            for p in presets:
                status = "✓" if p.is_active else "✗"
                typer.echo(f"  [{status}] {p.name} | {p.provider}/{p.model_name} | {p.litellm_model_string}")
    asyncio.run(_list())


@app.command()
def preset_create(
    name: str = typer.Option(..., prompt="预设名称"),
    provider: str = typer.Option(..., prompt="提供商(openai/anthropic/deepseek)"),
    model_name: str = typer.Option(..., prompt="模型名称"),
    litellm_string: str = typer.Option("", prompt="LiteLLM模型字符串"),
    api_key: str = typer.Option("", prompt="API Key (留空跳过)"),
):
    """创建新的模型预设"""
    async def _create():
        from src.core.database import async_session_factory
        from src.services.model_preset import ModelPresetService, ModelPresetCreate
        async with async_session_factory() as session:
            svc = ModelPresetService(session)
            data = ModelPresetCreate(
                name=name, provider=provider, model_name=model_name,
                litellm_model_string=litellm_string or f"{provider}/{model_name}",
                api_key_plaintext=api_key,
            )
            preset = await svc.create_preset(data)
            await session.commit()
            typer.echo(f"[OK] 模型预设 '{preset.name}' 已创建 (id={preset.id})")
    asyncio.run(_create())


@app.command()
def preset_delete(preset_id: str):
    """删除模型预设"""
    async def _delete():
        from src.core.database import async_session_factory
        from src.services.model_preset import ModelPresetService
        async with async_session_factory() as session:
            svc = ModelPresetService(session)
            await svc.delete_preset(uuid.UUID(preset_id))
            await session.commit()
            typer.echo(f"[OK] 模型预设已删除")
    asyncio.run(_delete())


# ─── 组织架构 ──────────────────────────────────────────

@app.command()
def org_tree():
    """查看组织架构树"""
    async def _tree():
        from src.core.database import async_session_factory
        from src.services.org_structure import OrgStructureService
        async with async_session_factory() as session:
            svc = OrgStructureService(session)
            tree = await svc.get_org_tree()

            def print_node(node, indent=0):
                prefix = "  " * indent
                icon = {0: "🏛", 1: "📦", 2: "📌"}.get(node["tier"], "  ")
                active = "" if node["is_active"] else " [已停用]"
                typer.echo(f"{prefix}├─ {icon} [T{node['tier']}] {node['name']} ({node['dept_type']}){active}")
                for child in node.get("children", []):
                    print_node(child, indent + 1)
            for root in tree:
                print_node(root)
    asyncio.run(_tree())


@app.command()
def org_list():
    """列出所有部门"""
    async def _list():
        from src.core.database import async_session_factory
        from src.services.org_structure import OrgStructureService
        async with async_session_factory() as session:
            svc = OrgStructureService(session)
            depts = await svc.list_departments()
            for d in sorted(depts, key=lambda x: (x.tier, x.sort_order)):
                parent = f" → {d.parent_id}" if d.parent_id else ""
                typer.echo(f"  [T{d.tier}] {d.name:20s} | {d.dept_type:12s} | {d.org_path}")
    asyncio.run(_list())


@app.command()
def org_create(
    name: str = typer.Option(..., prompt="部门名称"),
    tier: int = typer.Option(..., prompt="层级(T0=0, T1=1, T2=2)"),
    dept_type: str = typer.Option(..., prompt="类型(ceo_office/department/center/section/office)"),
    parent_name: str = typer.Option("", prompt="上级部门名称(T0留空)"),
    description: str = typer.Option("", prompt="描述"),
):
    """创建新部门"""
    async def _create():
        from src.core.database import async_session_factory
        from src.repositories.organization_repo import DepartmentRepository
        from src.services.org_structure import OrgStructureService, DepartmentCreate, OrgTier, DeptType
        async with async_session_factory() as session:
            svc = OrgStructureService(session)
            parent_id = None
            if parent_name:
                dept_repo = DepartmentRepository(session)
                parent = await dept_repo.get_by_name(parent_name)
                if not parent:
                    typer.echo(f"[错误] 上级部门 '{parent_name}' 不存在")
                    return
                parent_id = parent.id
            dept = await svc.create_department(DepartmentCreate(
                name=name, tier=OrgTier(tier), dept_type=DeptType(dept_type),
                parent_id=parent_id, description=description,
            ))
            await session.commit()
            typer.echo(f"[OK] 部门 '{dept.name}' 已创建 (id={dept.id})")
    asyncio.run(_create())


@app.command()
def org_delete(department_name: str):
    """删除部门（必须无子部门）"""
    async def _delete():
        from src.core.database import async_session_factory
        from src.repositories.organization_repo import DepartmentRepository
        from src.services.org_structure import OrgStructureService
        async with async_session_factory() as session:
            dept_repo = DepartmentRepository(session)
            dept = await dept_repo.get_by_name(department_name)
            if not dept:
                typer.echo(f"[错误] 部门 '{department_name}' 不存在")
                return
            svc = OrgStructureService(session)
            await svc.delete_department(dept.id)
            await session.commit()
            typer.echo(f"[OK] 部门 '{department_name}' 已删除")
    asyncio.run(_delete())


# ─── Agent管理 ──────────────────────────────────────────

@app.command()
def agent_list():
    """列出所有Agent"""
    async def _list():
        from src.core.database import async_session_factory
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        from src.models.organization import Agent as AgentModel
        async with async_session_factory() as session:
            result = await session.execute(
                select(AgentModel).options(selectinload(AgentModel.model_preset), selectinload(AgentModel.department))
            )
            agents = result.scalars().all()
            if not agents:
                typer.echo("(无Agent)")
                return
            for a in agents:
                status = "✓" if a.is_active else "✗"
                preset_name = a.model_preset.name if a.model_preset else "无预设"
                typer.echo(f"  [{status}] {a.name:20s} | {a.role:15s} | 模型:{preset_name}")
    asyncio.run(_list())


@app.command()
def agent_create(
    name: str = typer.Option(..., prompt="Agent名称"),
    role: str = typer.Option(..., prompt="角色"),
    department_name: str = typer.Option(..., prompt="所属部门名称"),
    preset_name: str = typer.Option("", prompt="模型预设名称(留空使用默认)"),
    reports_to: str = typer.Option("", prompt="汇报对象Agent名称(留空跳过)"),
):
    """创建新Agent"""
    async def _create():
        from src.core.database import async_session_factory
        from src.repositories.organization_repo import DepartmentRepository
        from src.repositories.agent_repo import AgentRepository, ModelPresetRepository
        from src.services.agent_lifecycle import AgentLifecycleService, AgentCreate
        async with async_session_factory() as session:
            dept_repo = DepartmentRepository(session)
            dept = await dept_repo.get_by_name(department_name)
            if not dept:
                typer.echo(f"[错误] 部门 '{department_name}' 不存在，请先创建或检查部门名称")
                return

            preset_id = None
            if preset_name:
                preset_repo = ModelPresetRepository(session)
                preset = await preset_repo.get_by_name(preset_name)
                if preset:
                    preset_id = preset.id
                else:
                    typer.echo(f"[警告] 模型预设 '{preset_name}' 不存在，将不设置模型")

            reports_to_id = None
            if reports_to:
                agent_repo = AgentRepository(session)
                superior = await agent_repo.get_by_name(reports_to)
                if superior:
                    reports_to_id = superior.id
                else:
                    typer.echo(f"[警告] Agent '{reports_to}' 不存在")

            svc = AgentLifecycleService(session)
            data = AgentCreate(
                name=name, role=role, department_id=dept.id,
                model_preset_id=preset_id, reports_to_agent_id=reports_to_id,
            )
            agent = await svc.create_agent(data)
            await session.commit()
            typer.echo(f"[OK] Agent '{agent.name}' 已创建")
            typer.echo(f"  文件夹: {agent.agent_folder_path}")
            typer.echo(f"  部门: {department_name} (T{dept.tier})")
    asyncio.run(_create())


@app.command()
def agent_show(agent_name: str):
    """查看Agent详情"""
    async def _show():
        from src.core.database import async_session_factory
        from src.repositories.agent_repo import AgentRepository
        from src.utils.file_system import read_agent_soul, read_agent_memory
        from src.core.config import settings
        async with async_session_factory() as session:
            repo = AgentRepository(session)
            agent = await repo.get_by_name(agent_name)
            if not agent:
                typer.echo(f"[错误] Agent '{agent_name}' 不存在")
                return
            typer.echo(f"名称: {agent.name}")
            typer.echo(f"角色: {agent.role}")
            typer.echo(f"状态: {'活跃' if agent.is_active else '停用'} ({agent.availability_status})")
            typer.echo(f"文件夹: {agent.agent_folder_path}")
            typer.echo(f"温度: {agent.temperature} | max_tokens: {agent.max_tokens}")
            typer.echo(f"记忆上限: {agent.max_memory_tokens} tokens")
            full_path = settings.project_root / agent.agent_folder_path
            typer.echo(f"\n--- soul.md ---")
            typer.echo(read_agent_soul(str(full_path))[:500])
    asyncio.run(_show())


@app.command()
def agent_deactivate(agent_name: str):
    """停用Agent"""
    async def _deactivate():
        from src.core.database import async_session_factory
        from src.repositories.agent_repo import AgentRepository
        from src.services.agent_lifecycle import AgentLifecycleService
        async with async_session_factory() as session:
            repo = AgentRepository(session)
            agent = await repo.get_by_name(agent_name)
            if not agent:
                typer.echo(f"[错误] Agent '{agent_name}' 不存在")
                return
            svc = AgentLifecycleService(session)
            await svc.deactivate_agent(agent.id)
            await session.commit()
            typer.echo(f"[OK] Agent '{agent_name}' 已停用")
    asyncio.run(_deactivate())


@app.command()
def agent_delete(agent_name: str):
    """删除Agent（同时删除文件夹）"""
    async def _delete():
        from src.core.database import async_session_factory
        from src.repositories.agent_repo import AgentRepository
        from src.services.agent_lifecycle import AgentLifecycleService
        async with async_session_factory() as session:
            repo = AgentRepository(session)
            agent = await repo.get_by_name(agent_name)
            if not agent:
                typer.echo(f"[错误] Agent '{agent_name}' 不存在")
                return
            svc = AgentLifecycleService(session)
            await svc.delete_agent(agent.id)
            await session.commit()
            typer.echo(f"[OK] Agent '{agent_name}' 已删除（含文件夹）")
    asyncio.run(_delete())


@app.command()
def agent_soul(agent_name: str):
    """查看Agent的soul.md内容"""
    async def _show():
        from src.core.database import async_session_factory
        from src.repositories.agent_repo import AgentRepository
        from src.utils.file_system import read_agent_soul
        from src.core.config import settings
        async with async_session_factory() as session:
            repo = AgentRepository(session)
            agent = await repo.get_by_name(agent_name)
            if not agent:
                typer.echo(f"[错误] Agent '{agent_name}' 不存在")
                return
            full_path = settings.project_root / agent.agent_folder_path
            typer.echo(read_agent_soul(str(full_path)))
    asyncio.run(_show())


# ─── 任务管理 ──────────────────────────────────────────

@app.command()
def task_list(status: str = typer.Option(None, help="按状态筛选")):
    """列出任务"""
    async def _list():
        from src.core.database import async_session_factory
        from src.services.task_manager import TaskManagerService
        async with async_session_factory() as session:
            svc = TaskManagerService(session)
            tasks = await svc.list_tasks(status=status)
            if not tasks:
                typer.echo("(无任务)")
                return
            icons = {"pending":"○","in_progress":"◉","completed":"✓","failed":"✗","needs_clarification":"?","cancelled":"⊘","blocked":"⊡"}
            for t in tasks:
                icon = icons.get(t.status, " ")
                typer.echo(f"  [{icon}] {t.task_code:20s} | {t.title[:50]:50s} | {t.status:20s} | {t.priority}")
    asyncio.run(_list())


@app.command()
def task_create(
    title: str = typer.Option(..., prompt="任务标题"),
    description: str = typer.Option("", prompt="描述"),
    priority: str = typer.Option("medium", prompt="优先级(critical/high/medium/low)"),
    assign_to: str = typer.Option("", prompt="分配给Agent名称(留空跳过)"),
    parent_code: str = typer.Option("", prompt="父任务编号(留空创建根任务)"),
):
    """创建新任务"""
    async def _create():
        from src.core.database import async_session_factory
        from src.repositories.agent_repo import AgentRepository
        from src.repositories.task_repo import TaskRepository
        from src.services.task_manager import TaskManagerService, TaskCreate, TaskPriority
        async with async_session_factory() as session:
            svc = TaskManagerService(session)
            agent_id = None
            if assign_to:
                agent_repo = AgentRepository(session)
                agent = await agent_repo.get_by_name(assign_to)
                if agent:
                    agent_id = agent.id
                else:
                    typer.echo(f"[警告] Agent '{assign_to}' 不存在")

            parent_id = None
            if parent_code:
                task_repo = TaskRepository(session)
                parent = await task_repo.get_by_code(parent_code)
                if parent:
                    parent_id = parent.id
                else:
                    typer.echo(f"[警告] 父任务 '{parent_code}' 不存在")

            task = await svc.create_task(TaskCreate(
                title=title, description=description, created_by="cli",
                priority=TaskPriority(priority), assigned_agent_id=agent_id,
                parent_task_id=parent_id,
            ))
            await session.commit()
            typer.echo(f"[OK] 任务 '{task.task_code}' 已创建")
            if parent_id:
                typer.echo(f"  父任务: {parent_code}")
    asyncio.run(_create())


@app.command()
def task_show(task_code: str):
    """查看任务详情和子树"""
    async def _show():
        from src.core.database import async_session_factory
        from src.repositories.task_repo import TaskRepository
        from src.services.task_manager import TaskManagerService
        async with async_session_factory() as session:
            repo = TaskRepository(session)
            task = await repo.get_by_code(task_code)
            if not task:
                typer.echo(f"[错误] 任务 '{task_code}' 不存在")
                return
            svc = TaskManagerService(session)
            breadcrumb = await svc.get_task_breadcrumb(task.id)
            chain = " → ".join(f"{b['task_code']}" for b in breadcrumb)
            typer.echo(f"链路: {chain}")
            typer.echo(f"编号: {task.task_code}")
            typer.echo(f"标题: {task.title}")
            typer.echo(f"状态: {task.status} | 优先级: {task.priority}")
            typer.echo(f"重试: {task.retry_count}/{task.max_retries} | 升级层级: {task.escalation_level}")
            if task.description:
                typer.echo(f"描述: {task.description[:200]}")

            deps = await repo.get_dependencies(task.id)
            if deps:
                typer.echo(f"依赖: {', '.join(str(d.depends_on_task_id) for d in deps)}")

            sub_tasks = await repo.list_sub_tasks(task.id)
            if sub_tasks:
                typer.echo(f"子任务 ({len(sub_tasks)}):")
                for st in sub_tasks:
                    typer.echo(f"  - [{st.status}] {st.task_code}: {st.title}")
    asyncio.run(_show())


@app.command()
def task_update(task_code: str, status: str = typer.Option(..., help="新状态: in_progress/completed/failed/needs_clarification/cancelled/retry")):
    """更新任务状态"""
    async def _update():
        from src.core.database import async_session_factory
        from src.repositories.task_repo import TaskRepository
        from src.services.task_manager import TaskManagerService
        async with async_session_factory() as session:
            repo = TaskRepository(session)
            task = await repo.get_by_code(task_code)
            if not task:
                typer.echo(f"[错误] 任务 '{task_code}' 不存在")
                return
            svc = TaskManagerService(session)
            status_map = {
                "in_progress": lambda: svc.mark_in_progress(task.id),
                "completed": lambda: svc.mark_completed(task.id),
                "failed": lambda: svc.mark_failed(task.id),
                "needs_clarification": lambda: svc.mark_needs_clarification(task.id),
                "cancelled": lambda: svc.cancel_task(task.id),
                "retry": lambda: svc.retry_task(task.id),
            }
            handler = status_map.get(status)
            if not handler:
                typer.echo(f"[错误] 不支持的状态: {status}")
                return
            updated = await handler()
            await session.commit()
            typer.echo(f"[OK] 任务 '{task_code}' 状态: {task.status} → {updated.status}")
    asyncio.run(_update())


@app.command()
def task_tree(task_code: str):
    """查看任务完整树"""
    async def _tree():
        from src.core.database import async_session_factory
        from src.repositories.task_repo import TaskRepository
        async with async_session_factory() as session:
            repo = TaskRepository(session)
            task = await repo.get_by_code(task_code)
            if not task:
                typer.echo(f"[错误] 任务 '{task_code}' 不存在")
                return
            tree = await repo.get_task_tree(task.id)

            def print_node(node, indent=0):
                t = node["task"]
                prefix = "  " * indent
                icon = {"pending":"○","in_progress":"◉","completed":"✓","failed":"✗"}.get(t.status," ")
                typer.echo(f"{prefix}[{icon}] {t.task_code}: {t.title} ({t.status})")
                for child in node.get("children", []):
                    print_node(child, indent + 1)

            print_node(tree)
    asyncio.run(_tree())


# ─── 会议管理 ──────────────────────────────────────────

@app.command()
def meeting_list():
    """列出所有会议"""
    async def _list():
        from src.core.database import async_session_factory
        from src.services.meeting_orchestrator import MeetingOrchestrator
        async with async_session_factory() as session:
            svc = MeetingOrchestrator(session)
            meetings = await svc.list_meetings()
            if not meetings:
                typer.echo("(无会议)")
                return
            icons = {"scheduled":"○","in_progress":"◉","adjourned":"◎","completed":"✓","cancelled":"✗","minutes_pending":"📝"}
            for m in meetings:
                icon = icons.get(m.status, " ")
                typer.echo(f"  [{icon}] {m.meeting_code:20s} | {m.title[:45]:45s} | {m.meeting_type:20s} | {m.status}")
    asyncio.run(_list())


@app.command()
def meeting_create(
    title: str = typer.Option(..., prompt="会议标题"),
    meeting_type: str = typer.Option("coordination", prompt="类型(coordination/user_direct/recruitment_review)"),
    secretary_name: str = typer.Option(..., prompt="秘书Agent名称"),
    chair_name: str = typer.Option("", prompt="主席Agent名称(留空自动)"),
    participants: str = typer.Option("", prompt="参会Agent名称(逗号分隔)"),
):
    """创建新会议"""
    async def _create():
        from src.core.database import async_session_factory
        from src.repositories.agent_repo import AgentRepository
        from src.services.meeting_orchestrator import MeetingOrchestrator, MeetingCreate
        from src.meeting.types import MeetingType
        async with async_session_factory() as session:
            agent_repo = AgentRepository(session)
            secretary = await agent_repo.get_by_name(secretary_name)
            if not secretary:
                typer.echo(f"[错误] 秘书Agent '{secretary_name}' 不存在")
                return
            chair_id = None
            if chair_name:
                chair = await agent_repo.get_by_name(chair_name)
                if chair:
                    chair_id = chair.id
                else:
                    typer.echo(f"[警告] 主席Agent '{chair_name}' 不存在")
            participant_ids = []
            if participants:
                for name in participants.split(","):
                    name = name.strip()
                    agent = await agent_repo.get_by_name(name)
                    if agent:
                        participant_ids.append(agent.id)
                    else:
                        typer.echo(f"[警告] Agent '{name}' 不存在")
            svc = MeetingOrchestrator(session)
            meeting = await svc.create_meeting(MeetingCreate(
                meeting_type=MeetingType(meeting_type),
                title=title, secretary_agent_id=secretary.id,
                chair_agent_id=chair_id, participant_agent_ids=participant_ids,
            ))
            await session.commit()
            typer.echo(f"[OK] 会议 '{meeting.meeting_code}' 已创建")
            typer.echo(f"  类型: {meeting_type} | 状态: {meeting.status}")
    asyncio.run(_create())


@app.command()
def meeting_show(meeting_code: str):
    """查看会议详情"""
    async def _show():
        from src.core.database import async_session_factory
        from src.repositories.meeting_repo import MeetingRepository
        from src.services.meeting_orchestrator import MeetingOrchestrator
        from src.meeting.protocol import meeting_protocol_registry
        async with async_session_factory() as session:
            repo = MeetingRepository(session)
            meeting = await repo.get_by_code(meeting_code)
            if not meeting:
                typer.echo(f"[错误] 会议 '{meeting_code}' 不存在")
                return
            typer.echo(f"编号: {meeting.meeting_code}")
            typer.echo(f"标题: {meeting.title}")
            typer.echo(f"类型: {meeting.meeting_type} | 状态: {meeting.status}")
            typer.echo(f"最大轮次: {meeting.max_turns}")
            engine = meeting_protocol_registry.get(meeting.id)
            if engine:
                typer.echo(f"实时: 已进行{engine.turn_count}轮 | 队列{engine.speaker_queue.pending_count}人")

            svc = MeetingOrchestrator(session)
            statements = await svc.get_statements(meeting.id)
            if statements:
                typer.echo(f"发言记录 ({len(statements)}):")
                for s in statements[-5:]:
                    typer.echo(f"  [{s.statement_type}] Agent {str(s.speaker_agent_id)[:8]}: {s.content[:80]}...")
    asyncio.run(_show())


@app.command()
def meeting_start(meeting_code: str):
    """开始会议"""
    async def _start():
        from src.core.database import async_session_factory
        from src.repositories.meeting_repo import MeetingRepository
        from src.services.meeting_orchestrator import MeetingOrchestrator
        async with async_session_factory() as session:
            repo = MeetingRepository(session)
            meeting = await repo.get_by_code(meeting_code)
            if not meeting:
                typer.echo(f"[错误] 会议 '{meeting_code}' 不存在")
                return
            svc = MeetingOrchestrator(session)
            engine = await svc.start_meeting(meeting.id)
            await session.commit()
            typer.echo(f"[OK] 会议 '{meeting_code}' 已开始")
            typer.echo(f"  参会人数: {engine.bus.subscriber_count if engine.bus else 0}")
    asyncio.run(_start())


@app.command()
def meeting_end(meeting_code: str):
    """结束会议（含终止前轮询）"""
    async def _end():
        from src.core.database import async_session_factory
        from src.repositories.meeting_repo import MeetingRepository
        from src.services.meeting_orchestrator import MeetingOrchestrator
        async with async_session_factory() as session:
            repo = MeetingRepository(session)
            meeting = await repo.get_by_code(meeting_code)
            if not meeting:
                typer.echo(f"[错误] 会议 '{meeting_code}' 不存在")
                return
            svc = MeetingOrchestrator(session)
            meeting = await svc.end_meeting(meeting.id)
            await session.commit()
            typer.echo(f"[OK] 会议 '{meeting_code}' 已休会（含轮询）")
    asyncio.run(_end())


# ─── 升级管理 ──────────────────────────────────────────

@app.command()
def escalation_list():
    """列出待处理升级"""
    async def _list():
        from src.core.database import async_session_factory
        from src.services.escalation_engine import EscalationEngine
        async with async_session_factory() as session:
            engine = EscalationEngine(session)
            pending = await engine.get_pending_escalations()
            if not pending:
                typer.echo("(无待处理升级)")
                return
            for e in pending:
                typer.echo(f"  [!] T{e.escalation_level} | 任务:{str(e.task_id)[:8]} | {e.reason} | → Agent {str(e.to_agent_id)[:8]}")
    asyncio.run(_list())


@app.command()
def escalation_analyze(task_code: str):
    """分析任务是否需要升级"""
    async def _analyze():
        from src.core.database import async_session_factory
        from src.repositories.task_repo import TaskRepository
        from src.services.escalation_engine import EscalationEngine
        async with async_session_factory() as session:
            repo = TaskRepository(session)
            task = await repo.get_by_code(task_code)
            if not task:
                typer.echo(f"[错误] 任务 '{task_code}' 不存在")
                return
            engine = EscalationEngine(session)
            analysis = await engine.analyze_failure(task.id)
            if not analysis:
                typer.echo(f"任务 '{task_code}' 状态正常，无需升级")
                return
            typer.echo(f"任务: {analysis.task_code}")
            typer.echo(f"原因: {analysis.reason.value}")
            typer.echo(f"详情: {analysis.error_detail}")
            typer.echo(f"分配Agent: {analysis.assigned_agent_name}")
    asyncio.run(_analyze())


@app.command()
def escalation_trigger(task_code: str, reason: str = "max_retries_exceeded"):
    """手动触发升级"""
    async def _trigger():
        from src.core.database import async_session_factory
        from src.repositories.task_repo import TaskRepository
        from src.services.escalation_engine import EscalationEngine, EscalationReason
        async with async_session_factory() as session:
            repo = TaskRepository(session)
            task = await repo.get_by_code(task_code)
            if not task:
                typer.echo(f"[错误] 任务 '{task_code}' 不存在")
                return
            engine = EscalationEngine(session)
            event = await engine.escalate(task.id, EscalationReason(reason))
            await session.commit()
            typer.echo(f"[OK] 任务 '{task_code}' 已升级 (L{event.escalation_level})")
            typer.echo(f"  升级到: Agent {str(event.to_agent_id)[:8]}")
    asyncio.run(_trigger())


@app.command()
def escalation_resolve(escalation_id: str, resolution: str = typer.Option(..., help="modify_and_retry/escalate_higher/resolve_directly/return_to_originator/cancelled"), resolved_by: str = typer.Option("", help="解决的Agent名称")):
    """解决升级事件"""
    async def _resolve():
        from src.core.database import async_session_factory
        from src.repositories.agent_repo import AgentRepository
        from src.services.escalation_engine import EscalationEngine, EscalationResolution
        async with async_session_factory() as session:
            agent_repo = AgentRepository(session)
            agent_id = None
            if resolved_by:
                agent = await agent_repo.get_by_name(resolved_by)
                if agent:
                    agent_id = agent.id
            engine = EscalationEngine(session)
            event = await engine.resolve_escalation(
                uuid.UUID(escalation_id), EscalationResolution(resolution),
                agent_id or uuid.uuid4(),
            )
            await session.commit()
            typer.echo(f"[OK] 升级已解决: {event.resolution}")
    asyncio.run(_resolve())


@app.command()
def watchdog_run():
    """运行一次任务看门狗检查"""
    from src.workers.task_watchdog import task_watchdog
    async def _run():
        await task_watchdog.check_all_tasks()
        typer.echo("[OK] 看门狗检查完成")
    asyncio.run(_run())


# ─── 日常运营 ──────────────────────────────────────────

@app.command()
def briefing_run():
    """运行一次每日简报生成"""
    from src.workers.daily_briefing import daily_briefing_pipeline
    async def _run():
        briefing = await daily_briefing_pipeline.run_once()
        if briefing:
            typer.echo(f"[OK] 每日简报已生成 (日期: {briefing.briefing_date})")
            typer.echo(briefing.content[:500])
        else:
            typer.echo("[OK] 今日简报已存在")
    asyncio.run(_run())


@app.command()
def workers_start():
    """启动所有后台Worker"""
    from src.workers.scheduler import scheduler
    async def _start():
        await scheduler.start_all()
        typer.echo("[OK] Worker已启动，按Ctrl+C停止...")
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            await scheduler.stop_all()
    asyncio.run(_start())


# ─── 服务 ──────────────────────────────────────────

@app.command()
def serve(host: str = "0.0.0.0", port: int = 8000):
    """启动FastAPI服务"""
    import uvicorn
    typer.echo(f"启动 {host}:{port} ...")
    uvicorn.run("src.api.app:app", host=host, port=port, reload=True)


if __name__ == "__main__":
    app()
