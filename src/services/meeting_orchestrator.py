import uuid
from dataclasses import dataclass, field
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.meeting import Meeting
from src.models.organization import Agent
from src.repositories.meeting_repo import MeetingRepository
from src.repositories.agent_repo import AgentRepository
from src.meeting.types import MeetingType, MeetingStatus
from src.meeting.protocol import MeetingProtocolEngine, meeting_protocol_registry
from src.core.config import settings
from src.core.exceptions import MeetingNotFoundError, MissingSecretariatError, PlatformError


@dataclass
class MeetingCreate:
    meeting_type: MeetingType
    title: str
    secretary_agent_id: uuid.UUID
    agenda: str = ""
    chair_agent_id: uuid.UUID | None = None
    participant_agent_ids: list[uuid.UUID] = field(default_factory=list)
    max_turns: int | None = None
    max_duration_minutes: int | None = None
    task_id: uuid.UUID | None = None
    parent_meeting_id: uuid.UUID | None = None
    meeting_context: dict | None = None


class MeetingOrchestrator:
    def __init__(self, session: AsyncSession):
        self.repo = MeetingRepository(session)
        self.agent_repo = AgentRepository(session)
        self.session = session

    async def create_meeting(self, data: MeetingCreate) -> Meeting:
        meeting_code = await self.repo.generate_meeting_code()

        # Validate secretary exists
        secretary = await self.agent_repo.get(data.secretary_agent_id)
        if not secretary:
            raise PlatformError(f"秘书Agent不存在: {data.secretary_agent_id}")

        # Validate chair if specified
        if data.chair_agent_id:
            chair = await self.agent_repo.get(data.chair_agent_id)
            if not chair:
                raise PlatformError(f"主席Agent不存在: {data.chair_agent_id}")

        # Ensure secretary is in participants
        all_participants = list(data.participant_agent_ids)
        if data.secretary_agent_id not in all_participants:
            all_participants.append(data.secretary_agent_id)
        if data.chair_agent_id and data.chair_agent_id not in all_participants:
            all_participants.append(data.chair_agent_id)

        meeting = Meeting(
            meeting_code=meeting_code,
            meeting_type=data.meeting_type.value,
            title=data.title,
            agenda=data.agenda,
            chair_agent_id=data.chair_agent_id,
            secretary_agent_id=data.secretary_agent_id,
            max_turns=data.max_turns or settings.meeting_max_turns_default,
            max_duration_minutes=data.max_duration_minutes or settings.meeting_max_duration_minutes_default,
            task_id=data.task_id,
            parent_meeting_id=data.parent_meeting_id,
            meeting_context=data.meeting_context or {},
        )
        meeting = await self.repo.create(meeting)

        # Add participants
        for agent_id in all_participants:
            role = "participant"
            if agent_id == data.chair_agent_id:
                role = "chair"
            elif agent_id == data.secretary_agent_id:
                role = "secretary"
            await self.repo.add_participant(meeting.id, agent_id, role=role, is_required=(role in ("chair", "secretary")))

        return meeting

    async def start_meeting(self, meeting_id: uuid.UUID) -> MeetingProtocolEngine:
        meeting = await self.repo.get(meeting_id)
        if not meeting:
            raise MeetingNotFoundError(f"会议不存在: {meeting_id}")

        if meeting.status != MeetingStatus.SCHEDULED.value:
            raise PlatformError(f"会议状态不允许开始: {meeting.status}")

        participants = await self.repo.get_participants(meeting_id)
        participant_ids = {p.agent_id for p in participants}

        engine = MeetingProtocolEngine(
            meeting_id=meeting_id,
            meeting_type=MeetingType(meeting.meeting_type),
            chair_agent_id=meeting.chair_agent_id,
            secretary_agent_id=meeting.secretary_agent_id,
        )
        engine.max_turns = meeting.max_turns
        engine.stalemate_threshold = meeting.stalemate_threshold
        engine.participant_ids = participant_ids

        await engine.start()
        meeting_protocol_registry.register(engine)

        meeting.status = MeetingStatus.IN_PROGRESS.value
        meeting.started_at = meeting.started_at or __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        await self.repo.update(meeting)

        return engine

    async def end_meeting(self, meeting_id: uuid.UUID) -> Meeting:
        meeting = await self.repo.get(meeting_id)
        if not meeting:
            raise MeetingNotFoundError(f"会议不存在: {meeting_id}")

        engine = meeting_protocol_registry.get(meeting_id)
        if engine:
            await engine.adjourn()
            meeting_protocol_registry.unregister(meeting_id)

        meeting.status = MeetingStatus.ADJOURNED.value
        meeting.ended_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        await self.repo.update(meeting)
        return meeting

    async def complete_meeting(self, meeting_id: uuid.UUID) -> Meeting:
        meeting = await self.repo.get(meeting_id)
        if not meeting:
            raise MeetingNotFoundError(f"会议不存在: {meeting_id}")
        meeting.status = MeetingStatus.COMPLETED.value
        return await self.repo.update(meeting)

    async def cancel_meeting(self, meeting_id: uuid.UUID) -> Meeting:
        meeting = await self.repo.get(meeting_id)
        if not meeting:
            raise MeetingNotFoundError(f"会议不存在: {meeting_id}")

        engine = meeting_protocol_registry.get(meeting_id)
        if engine:
            engine.cancel()
            meeting_protocol_registry.unregister(meeting_id)

        meeting.status = MeetingStatus.CANCELLED.value
        meeting.ended_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        return await self.repo.update(meeting)

    async def add_statement(self, meeting_id: uuid.UUID, speaker_id: uuid.UUID, content: str, statement_type: str = "general", reply_to_id: uuid.UUID | None = None, token_count: int | None = None):
        meeting = await self.repo.get(meeting_id)
        if not meeting:
            raise MeetingNotFoundError(f"会议不存在: {meeting_id}")

        # adjourned/cancelled/minutes_pending/completed 都是终态：会后写入的发言会混进纪要
        if meeting.status != MeetingStatus.IN_PROGRESS.value:
            raise PlatformError(f"会议当前状态不允许发言: {meeting.status}")

        participants = await self.repo.get_participants(meeting_id)
        if speaker_id not in {p.agent_id for p in participants}:
            raise PlatformError(f"发言人不在与会者名单中: {speaker_id}")

        engine = meeting_protocol_registry.get(meeting_id)
        if engine:
            await engine.record_statement(speaker_id, content, statement_type, token_count)

        stmt = await self.repo.add_statement(
            meeting_id=meeting_id, speaker_agent_id=speaker_id, content=content,
            turn_id=None, statement_type=statement_type, reply_to_id=reply_to_id,
            token_count=token_count,
        )
        return stmt

    async def add_turn(self, meeting_id: uuid.UUID, speaker_id: uuid.UUID, turn_type: str = "statement"):
        engine = meeting_protocol_registry.get(meeting_id)
        turn_number = engine.turn_count if engine else 1
        return await self.repo.add_turn(meeting_id, turn_number, speaker_id, turn_type)

    async def get_engine(self, meeting_id: uuid.UUID) -> MeetingProtocolEngine | None:
        return meeting_protocol_registry.get(meeting_id)

    async def get_meeting(self, meeting_id: uuid.UUID) -> Meeting:
        meeting = await self.repo.get(meeting_id)
        if not meeting:
            raise MeetingNotFoundError(f"会议不存在: {meeting_id}")
        return meeting

    async def get_statements(self, meeting_id: uuid.UUID):
        return await self.repo.get_statements(meeting_id)

    async def get_participants(self, meeting_id: uuid.UUID):
        return await self.repo.get_participants(meeting_id)

    async def list_meetings(self, status: str | None = None):
        return await self.repo.list_all(status=status)

    async def save_minutes(self, meeting_id: uuid.UUID, content: str, summary: str, action_items: list, decisions: list, generated_by: uuid.UUID):
        return await self.repo.save_minutes(meeting_id, content, summary, action_items, decisions, generated_by)

    async def get_minutes(self, meeting_id: uuid.UUID):
        return await self.repo.get_minutes(meeting_id)
