import pytest
from src.models.organization import Department, Agent
from src.services.task_manager import TaskManagerService, TaskCreate, TaskDecomposition, TaskStatus, TaskPriority
from src.repositories.task_repo import TaskRepository
from src.core.exceptions import InvalidStateTransitionError, CircularDependencyError


@pytest.fixture
async def setup_agent(db_session):
    dept = Department(name="测试部门", org_path="/test", tier=1, dept_type="department")
    db_session.add(dept)
    await db_session.flush()

    agent = Agent(name="测试Agent", role="测试", department_id=dept.id, agent_folder_path="agents/test/agent")
    db_session.add(agent)
    await db_session.flush()
    return agent.id, dept.id


@pytest.mark.asyncio
async def test_create_root_task(db_session, setup_agent):
    agent_id, dept_id = setup_agent
    svc = TaskManagerService(db_session)
    task = await svc.create_task(TaskCreate(
        title="根任务", created_by="test", assigned_agent_id=agent_id,
    ))
    assert task.task_code.startswith("T-")
    assert task.status == "pending"
    assert task.parent_task_id is None
    assert task.root_task_id is None


@pytest.mark.asyncio
async def test_create_sub_task(db_session, setup_agent):
    agent_id, dept_id = setup_agent
    svc = TaskManagerService(db_session)
    parent = await svc.create_task(TaskCreate(title="父任务", created_by="test"))
    child = await svc.create_task(TaskCreate(
        title="子任务", created_by="test", parent_task_id=parent.id,
    ))
    assert child.parent_task_id == parent.id
    assert child.root_task_id == parent.id
    assert child.task_code.startswith(parent.task_code)


@pytest.mark.asyncio
async def test_task_code_hierarchy(db_session, setup_agent):
    agent_id, dept_id = setup_agent
    svc = TaskManagerService(db_session)
    root = await svc.create_task(TaskCreate(title="根", created_by="test"))
    child1 = await svc.create_task(TaskCreate(title="子1", created_by="test", parent_task_id=root.id))
    child2 = await svc.create_task(TaskCreate(title="子2", created_by="test", parent_task_id=root.id))
    assert child1.task_code != child2.task_code
    assert child1.task_code.startswith(root.task_code)
    assert child2.task_code.startswith(root.task_code)


@pytest.mark.asyncio
async def test_status_transition_happy_path(db_session, setup_agent):
    agent_id, dept_id = setup_agent
    svc = TaskManagerService(db_session)
    task = await svc.create_task(TaskCreate(title="测试", created_by="test"))

    task = await svc.mark_in_progress(task.id)
    assert task.status == "in_progress"
    assert task.started_at is not None

    task = await svc.mark_completed(task.id)
    assert task.status == "completed"
    assert task.completed_at is not None


@pytest.mark.asyncio
async def test_invalid_transition_rejected(db_session, setup_agent):
    agent_id, dept_id = setup_agent
    svc = TaskManagerService(db_session)
    task = await svc.create_task(TaskCreate(title="测试", created_by="test"))

    with pytest.raises(InvalidStateTransitionError):
        # pending → completed 是不允许的（需先 in_progress）
        await svc.mark_completed(task.id)


@pytest.mark.asyncio
async def test_fail_and_retry(db_session, setup_agent):
    agent_id, dept_id = setup_agent
    svc = TaskManagerService(db_session)
    task = await svc.create_task(TaskCreate(title="测试", created_by="test", max_retries=2))

    task = await svc.mark_in_progress(task.id)
    task = await svc.mark_failed(task.id)
    assert task.status == "failed"

    task = await svc.retry_task(task.id)
    assert task.status == "pending"
    assert task.retry_count == 1

    task = await svc.mark_in_progress(task.id)
    task = await svc.mark_failed(task.id)
    task = await svc.retry_task(task.id)
    assert task.retry_count == 2


@pytest.mark.asyncio
async def test_max_retries_exceeded(db_session, setup_agent):
    agent_id, dept_id = setup_agent
    svc = TaskManagerService(db_session)
    task = await svc.create_task(TaskCreate(title="测试", created_by="test", max_retries=1))

    task = await svc.mark_in_progress(task.id)
    task = await svc.mark_failed(task.id)
    task = await svc.retry_task(task.id)
    assert task.retry_count == 1

    task = await svc.mark_in_progress(task.id)
    task = await svc.mark_failed(task.id)
    with pytest.raises(InvalidStateTransitionError):
        await svc.retry_task(task.id)


@pytest.mark.asyncio
async def test_task_decomposition(db_session, setup_agent):
    agent_id, dept_id = setup_agent
    svc = TaskManagerService(db_session)
    parent = await svc.create_task(TaskCreate(title="父任务", created_by="test"))

    sub_tasks = await svc.decompose_task(parent.id, [
        TaskDecomposition(title="子任务A", priority=TaskPriority.HIGH, assigned_agent_id=agent_id),
        TaskDecomposition(title="子任务B", priority=TaskPriority.MEDIUM),
    ])
    assert len(sub_tasks) == 2
    assert sub_tasks[0].priority == "high"
    assert sub_tasks[0].parent_task_id == parent.id
    assert sub_tasks[1].parent_task_id == parent.id


@pytest.mark.asyncio
async def test_dependency_cycle_detection(db_session, setup_agent):
    agent_id, dept_id = setup_agent
    repo = TaskRepository(db_session)
    svc = TaskManagerService(db_session)

    task_a = await svc.create_task(TaskCreate(title="任务A", created_by="test"))
    task_b = await svc.create_task(TaskCreate(title="任务B", created_by="test"))
    task_c = await svc.create_task(TaskCreate(title="任务C", created_by="test"))

    await repo.add_dependency(task_a.id, task_b.id)
    await repo.add_dependency(task_b.id, task_c.id)

    with pytest.raises(CircularDependencyError):
        # C → A 会形成 A→B→C→A 的环
        await repo.add_dependency(task_c.id, task_a.id)


@pytest.mark.asyncio
async def test_cancel_cascades_to_children(db_session, setup_agent):
    agent_id, dept_id = setup_agent
    svc = TaskManagerService(db_session)
    parent = await svc.create_task(TaskCreate(title="父任务", created_by="test"))
    await svc.decompose_task(parent.id, [
        TaskDecomposition(title="子A"), TaskDecomposition(title="子B"),
    ])

    parent = await svc.cancel_task(parent.id)
    repo = TaskRepository(db_session)
    children = await repo.list_sub_tasks(parent.id)
    for child in children:
        assert child.status == "cancelled"


@pytest.mark.asyncio
async def test_breadcrumb(db_session, setup_agent):
    agent_id, dept_id = setup_agent
    svc = TaskManagerService(db_session)
    root = await svc.create_task(TaskCreate(title="根", created_by="test"))
    child = await svc.create_task(TaskCreate(title="子", created_by="test", parent_task_id=root.id))
    grandchild = await svc.create_task(TaskCreate(title="孙", created_by="test", parent_task_id=child.id))

    breadcrumb = await svc.get_task_breadcrumb(grandchild.id)
    assert len(breadcrumb) == 3
    assert breadcrumb[0]["task_code"] == root.task_code
    assert breadcrumb[2]["task_code"] == grandchild.task_code


@pytest.mark.asyncio
async def test_task_completed_on_dependency(db_session, setup_agent):
    agent_id, dept_id = setup_agent
    repo = TaskRepository(db_session)
    svc = TaskManagerService(db_session)

    task_a = await svc.create_task(TaskCreate(title="依赖任务", created_by="test"))
    task_b = await svc.create_task(TaskCreate(title="被阻塞任务", created_by="test"))
    await repo.add_dependency(task_b.id, task_a.id)

    assert not await repo.are_all_dependencies_satisfied(task_b.id)

    await svc.mark_in_progress(task_a.id)
    await svc.mark_completed(task_a.id)

    assert await repo.are_all_dependencies_satisfied(task_b.id)
