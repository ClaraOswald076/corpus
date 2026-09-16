import uuid

import pytest
from src.models.organization import Department, Agent
from src.services.task_manager import TaskManagerService, TaskCreate, TaskStatus
from src.services.escalation_engine import EscalationEngine, EscalationReason, EscalationResolution
from src.core.exceptions import EscalationLimitExceededError, AgentNotFoundError


@pytest.fixture
async def setup_hierarchy(db_session):
    dept = Department(name="升级测试部门", org_path="/esc", tier=1, dept_type="department")
    db_session.add(dept)
    await db_session.flush()

    superior = Agent(name="上级Agent", role="部门负责人", department_id=dept.id, agent_folder_path="agents/esc/superior")
    db_session.add(superior)
    await db_session.flush()

    worker = Agent(name="执行Agent", role="执行者", department_id=dept.id,
                   agent_folder_path="agents/esc/worker", reports_to_agent_id=superior.id)
    db_session.add(worker)
    await db_session.flush()

    return {"dept_id": dept.id, "superior_id": superior.id, "worker_id": worker.id}


@pytest.mark.asyncio
async def test_analyze_failure(db_session, setup_hierarchy):
    ids = setup_hierarchy
    svc = TaskManagerService(db_session)
    task = await svc.create_task(TaskCreate(
        title="失败任务", created_by="test", assigned_agent_id=ids["worker_id"], max_retries=1,
    ))
    await svc.mark_in_progress(task.id)
    await svc.mark_failed(task.id)
    await svc.retry_task(task.id)
    await svc.mark_in_progress(task.id)
    await svc.mark_failed(task.id)

    engine = EscalationEngine(db_session)
    analysis = await engine.analyze_failure(task.id)
    assert analysis is not None
    assert analysis.reason == EscalationReason.MAX_RETRIES_EXCEEDED
    assert analysis.assigned_agent_name == "执行Agent"


@pytest.mark.asyncio
async def test_escalate_up_chain(db_session, setup_hierarchy):
    ids = setup_hierarchy
    svc = TaskManagerService(db_session)
    task = await svc.create_task(TaskCreate(
        title="升级任务", created_by="test", assigned_agent_id=ids["worker_id"], max_retries=1,
    ))
    await svc.mark_in_progress(task.id)
    await svc.mark_failed(task.id)
    await svc.retry_task(task.id)
    await svc.mark_in_progress(task.id)
    await svc.mark_failed(task.id)

    engine = EscalationEngine(db_session)
    event = await engine.escalate(task.id, EscalationReason.MAX_RETRIES_EXCEEDED, ids["worker_id"])
    assert event is not None
    assert event.to_agent_id == ids["superior_id"]  # Goes up the reports_to chain
    assert event.escalation_level == 1
    assert task.escalation_level == 1


@pytest.mark.asyncio
async def test_escalation_cooldown(db_session, setup_hierarchy):
    ids = setup_hierarchy
    svc = TaskManagerService(db_session)
    task = await svc.create_task(TaskCreate(
        title="冷却测试", created_by="test", assigned_agent_id=ids["worker_id"], max_retries=0,
    ))
    await svc.mark_in_progress(task.id)
    await svc.mark_failed(task.id)

    engine = EscalationEngine(db_session)
    event1 = await engine.escalate(task.id, EscalationReason.MAX_RETRIES_EXCEEDED)
    event2 = await engine.escalate(task.id, EscalationReason.MAX_RETRIES_EXCEEDED)
    # Second escalation should be the same event (cooldown)
    assert event1.id == event2.id


@pytest.mark.asyncio
async def test_resolve_modify_and_retry(db_session, setup_hierarchy):
    ids = setup_hierarchy
    svc = TaskManagerService(db_session)
    task = await svc.create_task(TaskCreate(
        title="重试测试", created_by="test", assigned_agent_id=ids["worker_id"], max_retries=2,
    ))
    await svc.mark_in_progress(task.id)
    await svc.mark_failed(task.id)
    await svc.retry_task(task.id)
    await svc.mark_in_progress(task.id)
    await svc.mark_failed(task.id)

    engine = EscalationEngine(db_session)
    event = await engine.escalate(task.id, EscalationReason.MAX_RETRIES_EXCEEDED)
    await engine.resolve_escalation(event.id, EscalationResolution.MODIFY_AND_RETRY, ids["superior_id"])

    assert event.resolution == "modify_and_retry"
    assert task.status == "pending"
    assert task.retry_count == 0  # Reset


@pytest.mark.asyncio
async def test_resolve_cancel(db_session, setup_hierarchy):
    ids = setup_hierarchy
    svc = TaskManagerService(db_session)
    task = await svc.create_task(TaskCreate(
        title="取消测试", created_by="test", assigned_agent_id=ids["worker_id"], max_retries=0,
    ))
    await svc.mark_in_progress(task.id)
    await svc.mark_failed(task.id)

    engine = EscalationEngine(db_session)
    event = await engine.escalate(task.id, EscalationReason.MAX_RETRIES_EXCEEDED)
    await engine.resolve_escalation(event.id, EscalationResolution.CANCELLED, ids["superior_id"])

    assert event.resolution == "cancelled"
    assert task.status == "cancelled"


@pytest.mark.asyncio
async def test_escalation_max_depth(db_session, setup_hierarchy):
    ids = setup_hierarchy
    svc = TaskManagerService(db_session)
    task = await svc.create_task(TaskCreate(
        title="深度测试", created_by="test", assigned_agent_id=ids["worker_id"], max_retries=0,
    ))
    await svc.mark_in_progress(task.id)
    await svc.mark_failed(task.id)

    # Manually set escalation to max
    task.escalation_level = 3
    await db_session.flush()

    engine = EscalationEngine(db_session)
    with pytest.raises(EscalationLimitExceededError):
        await engine.escalate(task.id, EscalationReason.CRITICAL_FAILURE)


@pytest.mark.asyncio
async def test_get_pending_escalations(db_session, setup_hierarchy):
    ids = setup_hierarchy
    svc = TaskManagerService(db_session)
    task = await svc.create_task(TaskCreate(
        title="待处理测试", created_by="test", assigned_agent_id=ids["worker_id"], max_retries=0,
    ))
    await svc.mark_in_progress(task.id)
    await svc.mark_failed(task.id)

    engine = EscalationEngine(db_session)
    await engine.escalate(task.id, EscalationReason.MAX_RETRIES_EXCEEDED)

    pending = await engine.get_pending_escalations()
    assert len(pending) >= 1
    assert any(e.task_id == task.id for e in pending)

    pending_for_superior = await engine.get_pending_escalations(agent_id=ids["superior_id"])
    assert len(pending_for_superior) >= 1


@pytest.mark.asyncio
async def test_needs_clarification_escalation(db_session, setup_hierarchy):
    ids = setup_hierarchy
    svc = TaskManagerService(db_session)
    task = await svc.create_task(TaskCreate(
        title="需澄清", created_by="test", assigned_agent_id=ids["worker_id"],
    ))
    await svc.mark_in_progress(task.id)
    await svc.mark_needs_clarification(task.id, "不清楚需求")

    engine = EscalationEngine(db_session)
    analysis = await engine.analyze_failure(task.id)
    assert analysis is not None
    assert analysis.reason == EscalationReason.NEEDS_CLARIFICATION

    event = await engine.escalate(task.id, EscalationReason.NEEDS_CLARIFICATION)
    assert event.reason == "needs_clarification"


@pytest.mark.asyncio
async def test_escalate_from_department_follows_agent(db_session, setup_hierarchy):
    ids = setup_hierarchy
    svc = TaskManagerService(db_session)
    task = await svc.create_task(TaskCreate(
        title="无部门任务", created_by="test", assigned_agent_id=ids["worker_id"], max_retries=0,
    ))
    await svc.mark_in_progress(task.id)
    await svc.mark_failed(task.id)

    engine = EscalationEngine(db_session)
    event = await engine.escalate(task.id, EscalationReason.MAX_RETRIES_EXCEEDED)
    # from_department_id 取执行 Agent 的部门，而不是编造 uuid
    assert event.from_agent_id == ids["worker_id"]
    assert event.from_department_id == ids["dept_id"]
    assert event.to_department_id == ids["dept_id"]


@pytest.mark.asyncio
async def test_escalate_without_agent_raises(db_session, setup_hierarchy):
    ids = setup_hierarchy
    svc = TaskManagerService(db_session)
    task = await svc.create_task(TaskCreate(
        title="部门任务", created_by="test", assigned_department_id=ids["dept_id"], max_retries=0,
    ))
    await svc.mark_in_progress(task.id)
    await svc.mark_failed(task.id)

    engine = EscalationEngine(db_session)
    with pytest.raises(EscalationLimitExceededError):
        await engine.escalate(task.id, EscalationReason.MAX_RETRIES_EXCEEDED)
    # 不留任何伪造来源的升级记录
    assert await engine.get_escalations(task_id=task.id) == []


@pytest.mark.asyncio
async def test_resolve_without_resolver_stores_null(db_session, setup_hierarchy):
    ids = setup_hierarchy
    svc = TaskManagerService(db_session)
    task = await svc.create_task(TaskCreate(
        title="匿名解决", created_by="test", assigned_agent_id=ids["worker_id"], max_retries=0,
    ))
    await svc.mark_in_progress(task.id)
    await svc.mark_failed(task.id)

    engine = EscalationEngine(db_session)
    event = await engine.escalate(task.id, EscalationReason.MAX_RETRIES_EXCEEDED)
    resolved = await engine.resolve_escalation(event.id, EscalationResolution.MODIFY_AND_RETRY, None)
    assert resolved.resolved_by_agent_id is None
    assert resolved.resolution == "modify_and_retry"


@pytest.mark.asyncio
async def test_resolve_unknown_resolver_raises(db_session, setup_hierarchy):
    ids = setup_hierarchy
    svc = TaskManagerService(db_session)
    task = await svc.create_task(TaskCreate(
        title="查无此人", created_by="test", assigned_agent_id=ids["worker_id"], max_retries=0,
    ))
    await svc.mark_in_progress(task.id)
    await svc.mark_failed(task.id)

    engine = EscalationEngine(db_session)
    event = await engine.escalate(task.id, EscalationReason.MAX_RETRIES_EXCEEDED)
    with pytest.raises(AgentNotFoundError):
        await engine.resolve_escalation(
            event.id, EscalationResolution.MODIFY_AND_RETRY, uuid.uuid4(),
        )


@pytest.mark.asyncio
async def test_escalate_single_head_department_does_not_target_self(db_session):
    dept = Department(name="单人部门", org_path="/solo", tier=1, dept_type="department")
    db_session.add(dept)
    await db_session.flush()

    head = Agent(name="光杆负责人", role="部门负责人", department_id=dept.id, agent_folder_path="agents/solo/head")
    db_session.add(head)
    await db_session.flush()

    svc = TaskManagerService(db_session)
    task = await svc.create_task(TaskCreate(
        title="单人部门失败任务", created_by="test", assigned_agent_id=head.id, max_retries=0,
    ))
    await svc.mark_in_progress(task.id)
    await svc.mark_failed(task.id)

    engine = EscalationEngine(db_session)
    # 兜底选不出第二个人：明确拒绝请人工介入，而不是把升级事件写给自己
    with pytest.raises(EscalationLimitExceededError):
        await engine.escalate(task.id, EscalationReason.MAX_RETRIES_EXCEEDED)
    assert await engine.get_escalations(task_id=task.id) == []


@pytest.mark.asyncio
async def test_escalate_fallback_skips_requester(db_session):
    dept = Department(name="双人部门", org_path="/duo", tier=1, dept_type="department")
    db_session.add(dept)
    await db_session.flush()

    head_a = Agent(name="负责人甲", role="部门负责人", department_id=dept.id, agent_folder_path="agents/duo/a")
    head_b = Agent(name="负责人乙", role="部门负责人", department_id=dept.id, agent_folder_path="agents/duo/b")
    db_session.add_all([head_a, head_b])
    await db_session.flush()

    svc = TaskManagerService(db_session)
    task = await svc.create_task(TaskCreate(
        title="双人部门失败任务", created_by="test", assigned_agent_id=head_a.id, max_retries=0,
    ))
    await svc.mark_in_progress(task.id)
    await svc.mark_failed(task.id)

    engine = EscalationEngine(db_session)
    event = await engine.escalate(task.id, EscalationReason.MAX_RETRIES_EXCEEDED)
    # 兜底跳过发起人本人，落到同部门另一位负责人头上
    assert event.from_agent_id == head_a.id
    assert event.to_agent_id == head_b.id
