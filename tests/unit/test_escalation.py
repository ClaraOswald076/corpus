import pytest
from src.models.organization import Department, Agent
from src.services.task_manager import TaskManagerService, TaskCreate, TaskStatus
from src.services.escalation_engine import EscalationEngine, EscalationReason, EscalationResolution
from src.core.exceptions import EscalationLimitExceededError


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
async def test_escalation_cooldown_after_reload(db_session, setup_hierarchy):
    """Cooldown must survive a fresh DB read (SQLite returns naive created_at)."""
    ids = setup_hierarchy
    svc = TaskManagerService(db_session)
    task = await svc.create_task(TaskCreate(
        title="冷却重读", created_by="test", assigned_agent_id=ids["worker_id"], max_retries=0,
    ))
    await svc.mark_in_progress(task.id)
    await svc.mark_failed(task.id)

    engine = EscalationEngine(db_session)
    event1 = await engine.escalate(task.id, EscalationReason.MAX_RETRIES_EXCEEDED)
    db_session.expire(event1)  # force the next read to come from SQLite (naive)
    event2 = await engine.escalate(task.id, EscalationReason.MAX_RETRIES_EXCEEDED)
    assert event2.id == event1.id
