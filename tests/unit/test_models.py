import pytest
from src.models.organization import Department, Agent
from src.models.agent import ModelPreset, SoulDocument
from src.models.task import Task
from src.models.meeting import Meeting, MeetingParticipant


@pytest.mark.asyncio
async def test_create_department(db_session):
    dept = Department(name="测试部门", org_path="/test_dept", tier=1, dept_type="department")
    db_session.add(dept)
    await db_session.flush()
    assert dept.id is not None
    assert dept.tier == 1
    assert dept.name == "测试部门"


@pytest.mark.asyncio
async def test_create_model_preset(db_session):
    preset = ModelPreset(
        name="test-preset",
        provider="openai",
        model_name="gpt-4o",
        litellm_model_string="openai/gpt-4o",
    )
    db_session.add(preset)
    await db_session.flush()
    assert preset.id is not None
    assert preset.name == "test-preset"


@pytest.mark.asyncio
async def test_create_agent(db_session):
    dept = Department(name="测试部门2", org_path="/test_dept2", tier=1, dept_type="department")
    db_session.add(dept)
    await db_session.flush()

    agent = Agent(
        name="测试Agent",
        role="测试角色",
        department_id=dept.id,
        agent_folder_path="agents/test_dept2/test_agent",
    )
    db_session.add(agent)
    await db_session.flush()
    assert agent.id is not None
    assert agent.name == "测试Agent"


@pytest.mark.asyncio
async def test_create_task(db_session):
    task = Task(
        task_code="T-20250525-001",
        title="测试任务",
        status="pending",
        priority="medium",
        created_by="user",
    )
    db_session.add(task)
    await db_session.flush()
    assert task.id is not None
    assert task.status == "pending"


@pytest.mark.asyncio
async def test_create_meeting(db_session):
    dept = Department(name="会议测试部门", org_path="/meeting_dept", tier=1, dept_type="department")
    db_session.add(dept)
    await db_session.flush()

    agent = Agent(name="会议Agent", role="测试", department_id=dept.id, agent_folder_path="agents/meeting/test")
    secretary = Agent(name="秘书Agent", role="秘书", department_id=dept.id, agent_folder_path="agents/meeting/sec")
    db_session.add_all([agent, secretary])
    await db_session.flush()

    meeting = Meeting(
        meeting_code="MTG-20250525-001",
        meeting_type="coordination",
        title="测试会议",
        secretary_agent_id=secretary.id,
    )
    db_session.add(meeting)
    await db_session.flush()

    participant = MeetingParticipant(
        meeting_id=meeting.id,
        agent_id=agent.id,
        role="participant",
        is_required=True,
    )
    db_session.add(participant)
    await db_session.flush()

    assert meeting.id is not None
    assert meeting.status == "scheduled"


@pytest.mark.asyncio
async def test_department_hierarchy(db_session):
    parent = Department(name="上级部门", org_path="/parent", tier=0, dept_type="ceo_office")
    db_session.add(parent)
    await db_session.flush()

    child = Department(name="下级部门", parent_id=parent.id, org_path="/parent/child", tier=1, dept_type="department")
    db_session.add(child)
    await db_session.flush()

    assert child.parent_id == parent.id
    assert child.tier == 1
