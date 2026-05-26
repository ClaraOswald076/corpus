import uuid
import pytest
from src.models.organization import Department, Agent
from src.services.meeting_orchestrator import MeetingOrchestrator, MeetingCreate
from src.meeting.types import MeetingType, MeetingStatus
from src.meeting.message_bus import MeetingMessageBus, MessageType, MeetingMessage
from src.meeting.speaker_queue import SpeakerQueue, RequestToSpeak
from src.meeting.protocol import MeetingProtocolEngine
from src.core.exceptions import MissingSecretariatError


@pytest.fixture
async def setup_meeting_agents(db_session):
    dept = Department(name="会议测试部门", org_path="/mtg", tier=1, dept_type="department")
    db_session.add(dept)
    await db_session.flush()

    agents = {}
    for name in ["主席", "秘书", "产品经理", "开发工程师", "研究员"]:
        agent = Agent(name=name, role=name, department_id=dept.id, agent_folder_path=f"agents/mtg/{name}")
        db_session.add(agent)
        agents[name] = agent
    await db_session.flush()

    return {k: v.id for k, v in agents.items()}, dept.id


@pytest.mark.asyncio
async def test_create_meeting(db_session, setup_meeting_agents):
    agent_ids, dept_id = setup_meeting_agents
    svc = MeetingOrchestrator(db_session)
    meeting = await svc.create_meeting(MeetingCreate(
        meeting_type=MeetingType.COORDINATION,
        title="测试协调会",
        secretary_agent_id=agent_ids["秘书"],
        chair_agent_id=agent_ids["主席"],
        participant_agent_ids=[agent_ids["产品经理"], agent_ids["开发工程师"]],
    ))
    assert meeting.meeting_code.startswith("MTG-")
    assert meeting.status == "scheduled"
    assert meeting.secretary_agent_id == agent_ids["秘书"]

    participants = await svc.get_participants(meeting.id)
    participant_ids = {p.agent_id for p in participants}
    assert agent_ids["秘书"] in participant_ids
    assert agent_ids["主席"] in participant_ids
    assert agent_ids["产品经理"] in participant_ids


@pytest.mark.asyncio
async def test_meeting_must_have_secretariat(db_session, setup_meeting_agents):
    agent_ids, dept_id = setup_meeting_agents
    svc = MeetingOrchestrator(db_session)
    meeting = await svc.create_meeting(MeetingCreate(
        meeting_type=MeetingType.COORDINATION,
        title="无秘书会议",
        secretary_agent_id=agent_ids["秘书"],
        chair_agent_id=agent_ids["主席"],
        participant_agent_ids=[agent_ids["产品经理"]],
    ))
    await svc.start_meeting(meeting.id)


@pytest.mark.asyncio
async def test_start_and_end_meeting(db_session, setup_meeting_agents):
    agent_ids, dept_id = setup_meeting_agents
    svc = MeetingOrchestrator(db_session)
    meeting = await svc.create_meeting(MeetingCreate(
        meeting_type=MeetingType.COORDINATION,
        title="完整生命周期测试",
        secretary_agent_id=agent_ids["秘书"],
        chair_agent_id=agent_ids["主席"],
        participant_agent_ids=[agent_ids["产品经理"]],
    ))

    engine = await svc.start_meeting(meeting.id)
    assert engine.status == MeetingStatus.IN_PROGRESS
    assert engine.bus is not None
    assert engine.bus.subscriber_count >= 2

    await svc.end_meeting(meeting.id)
    assert meeting.status == MeetingStatus.ADJOURNED.value


@pytest.mark.asyncio
async def test_message_bus_pub_sub():
    mid = uuid.uuid4()
    bus = MeetingMessageBus(mid)

    agent_a = uuid.uuid4()
    agent_b = uuid.uuid4()

    queue_a = await bus.subscribe(agent_a)
    queue_b = await bus.subscribe(agent_b)

    msg = MeetingMessage(
        message_type=MessageType.STATEMENT,
        sender_agent_id=agent_a,
        content="Hello, this is Agent A",
    )
    await bus.publish(msg)

    received_a = await queue_a.get()
    received_b = await queue_b.get()

    assert received_a.content == "Hello, this is Agent A"
    assert received_b.content == "Hello, this is Agent A"
    assert len(bus.get_history()) == 1


@pytest.mark.asyncio
async def test_late_joining_agent_gets_history():
    mid = uuid.uuid4()
    bus = MeetingMessageBus(mid)

    agent_a = uuid.uuid4()
    agent_b = uuid.uuid4()

    queue_a = await bus.subscribe(agent_a)
    msg1 = MeetingMessage(message_type=MessageType.STATEMENT, sender_agent_id=agent_a, content="First")
    msg2 = MeetingMessage(message_type=MessageType.STATEMENT, sender_agent_id=agent_a, content="Second")
    await bus.publish(msg1)
    await bus.publish(msg2)

    # Agent B joins late
    queue_b = await bus.subscribe(agent_b)
    # Should get history
    hist_b = []
    while not queue_b.empty():
        hist_b.append(await queue_b.get())
    assert len(hist_b) == 2


@pytest.mark.asyncio
async def test_speaker_queue_priority():
    q = SpeakerQueue()
    agent_a = uuid.uuid4()
    agent_b = uuid.uuid4()
    agent_c = uuid.uuid4()

    q.submit(RequestToSpeak(agent_a, "A", urgency=8, topic_relevance=0.9, reference_to_prior="引用发言"))
    q.submit(RequestToSpeak(agent_b, "B", urgency=3, topic_relevance=0.5))
    q.submit(RequestToSpeak(agent_c, "C", urgency=5, topic_relevance=0.7))

    next_speaker = q.get_next()
    assert next_speaker.agent_id == agent_a  # Highest urgency + reference bonus

    q.mark_spoken(agent_a)
    next_speaker = q.get_next()
    assert next_speaker.agent_id == agent_c


@pytest.mark.asyncio
async def test_speaker_queue_deduplicate():
    q = SpeakerQueue()
    agent_a = uuid.uuid4()
    q.submit(RequestToSpeak(agent_a, "A", urgency=1))
    q.submit(RequestToSpeak(agent_a, "A", urgency=10))  # Same agent, higher urgency
    assert q.pending_count == 1
    assert q.get_next().urgency == 10


@pytest.mark.asyncio
async def test_statement_recording(db_session, setup_meeting_agents):
    agent_ids, dept_id = setup_meeting_agents
    svc = MeetingOrchestrator(db_session)
    meeting = await svc.create_meeting(MeetingCreate(
        meeting_type=MeetingType.COORDINATION, title="发言记录测试",
        secretary_agent_id=agent_ids["秘书"], chair_agent_id=agent_ids["主席"],
        participant_agent_ids=[agent_ids["产品经理"]],
    ))

    await svc.start_meeting(meeting.id)
    await svc.add_statement(meeting.id, agent_ids["产品经理"], "我认为应该优先处理A功能")
    await svc.add_statement(meeting.id, agent_ids["主席"], "请说明理由")

    statements = await svc.get_statements(meeting.id)
    assert len(statements) == 2
    assert "A功能" in statements[0].content
    assert "请说明理由" in statements[1].content


@pytest.mark.asyncio
async def test_request_to_speak_flow(db_session, setup_meeting_agents):
    agent_ids, dept_id = setup_meeting_agents
    svc = MeetingOrchestrator(db_session)
    meeting = await svc.create_meeting(MeetingCreate(
        meeting_type=MeetingType.COORDINATION, title="发言请求测试",
        secretary_agent_id=agent_ids["秘书"], chair_agent_id=agent_ids["主席"],
        participant_agent_ids=[agent_ids["产品经理"], agent_ids["开发工程师"]],
    ))

    engine = await svc.start_meeting(meeting.id)
    await engine.submit_request_to_speak(agent_ids["产品经理"], "产品经理", urgency=7)
    await engine.submit_request_to_speak(agent_ids["开发工程师"], "开发工程师", urgency=5)

    assert engine.speaker_queue.pending_count == 2

    next_id = await engine.grant_next_speaker()
    assert next_id == agent_ids["产品经理"]  # Higher urgency

    next_id = await engine.grant_next_speaker()
    assert next_id == agent_ids["开发工程师"]

    # No more requests
    next_id = await engine.grant_next_speaker()
    assert next_id is None


@pytest.mark.asyncio
async def test_should_continue_logic(db_session, setup_meeting_agents):
    agent_ids, dept_id = setup_meeting_agents
    svc = MeetingOrchestrator(db_session)
    meeting = await svc.create_meeting(MeetingCreate(
        meeting_type=MeetingType.COORDINATION, title="继续判断测试",
        secretary_agent_id=agent_ids["秘书"], chair_agent_id=agent_ids["主席"],
        participant_agent_ids=[agent_ids["产品经理"]],
    ))

    engine = await svc.start_meeting(meeting.id)
    # Just started, no turns yet → should continue (wait for someone to speak)
    assert engine.should_continue()
    # Simulate a turn happening
    engine.turn_count = 1
    engine.speaker_queue.mark_spoken(agent_ids["主席"])
    # Now: someone has spoken, no pending requests → should stop
    assert not engine.should_continue()


@pytest.mark.asyncio
async def test_minutes_save_and_retrieve(db_session, setup_meeting_agents):
    agent_ids, dept_id = setup_meeting_agents
    svc = MeetingOrchestrator(db_session)
    meeting = await svc.create_meeting(MeetingCreate(
        meeting_type=MeetingType.COORDINATION, title="纪要测试",
        secretary_agent_id=agent_ids["秘书"], chair_agent_id=agent_ids["主席"],
        participant_agent_ids=[agent_ids["产品经理"]],
    ))

    await svc.save_minutes(meeting.id,
        content="## 会议纪要\n\n讨论内容...\n\n## 决策\n1. 通过方案A",
        summary="讨论并通过了方案A",
        action_items=[{"assignee": "产品经理", "task": "起草方案A执行计划"}],
        decisions=[{"decision": "通过方案A", "voting": "一致同意"}],
        generated_by=agent_ids["秘书"],
    )

    minutes = await svc.get_minutes(meeting.id)
    assert minutes is not None
    assert "方案A" in minutes.content
    assert len(minutes.action_items) == 1
    assert len(minutes.decisions) == 1
    assert minutes.summary == "讨论并通过了方案A"


@pytest.mark.asyncio
async def test_meeting_cancellation(db_session, setup_meeting_agents):
    agent_ids, dept_id = setup_meeting_agents
    svc = MeetingOrchestrator(db_session)
    meeting = await svc.create_meeting(MeetingCreate(
        meeting_type=MeetingType.COORDINATION, title="取消测试",
        secretary_agent_id=agent_ids["秘书"],
        participant_agent_ids=[agent_ids["产品经理"]],
    ))

    await svc.start_meeting(meeting.id)
    meeting = await svc.cancel_meeting(meeting.id)
    assert meeting.status == MeetingStatus.CANCELLED.value
