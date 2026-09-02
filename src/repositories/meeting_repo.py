import uuid
from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.meeting import Meeting, MeetingParticipant, MeetingTurn, MeetingStatement, MeetingMinutes
from src.core.exceptions import MeetingNotFoundError, MissingSecretariatError


class MeetingRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, meeting_id: uuid.UUID) -> Meeting | None:
        return await self.session.get(Meeting, meeting_id)

    async def get_by_code(self, code: str) -> Meeting | None:
        result = await self.session.execute(select(Meeting).where(Meeting.meeting_code == code))
        return result.scalar_one_or_none()

    async def list_all(self, status: str | None = None, limit: int = 50) -> list[Meeting]:
        stmt = select(Meeting).order_by(Meeting.created_at.desc()).limit(limit)
        if status:
            stmt = stmt.where(Meeting.status == status)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, meeting: Meeting) -> Meeting:
        self.session.add(meeting)
        await self.session.flush()
        return meeting

    async def update(self, meeting: Meeting) -> Meeting:
        await self.session.flush()
        return meeting

    async def generate_meeting_code(self) -> str:
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        result = await self.session.execute(
            select(func.count(Meeting.id)).where(Meeting.meeting_code.like(f"MTG-{today}-%"))
        )
        count = result.scalar() or 0
        return f"MTG-{today}-{count + 1:03d}"

    async def add_participant(self, meeting_id: uuid.UUID, agent_id: uuid.UUID, role: str = "participant", is_required: bool = False) -> MeetingParticipant:
        p = MeetingParticipant(meeting_id=meeting_id, agent_id=agent_id, role=role, is_required=is_required)
        self.session.add(p)
        await self.session.flush()
        return p

    async def get_participants(self, meeting_id: uuid.UUID) -> list[MeetingParticipant]:
        result = await self.session.execute(select(MeetingParticipant).where(MeetingParticipant.meeting_id == meeting_id))
        return list(result.scalars().all())

    async def get_participant(self, meeting_id: uuid.UUID, agent_id: uuid.UUID) -> MeetingParticipant | None:
        result = await self.session.execute(
            select(MeetingParticipant).where(
                MeetingParticipant.meeting_id == meeting_id,
                MeetingParticipant.agent_id == agent_id,
            )
        )
        return result.scalar_one_or_none()

    async def add_turn(self, meeting_id: uuid.UUID, turn_number: int, speaker_agent_id: uuid.UUID, turn_type: str = "statement") -> MeetingTurn:
        t = MeetingTurn(meeting_id=meeting_id, turn_number=turn_number, speaker_agent_id=speaker_agent_id, turn_type=turn_type)
        self.session.add(t)
        await self.session.flush()
        return t

    async def update_turn(self, turn: MeetingTurn) -> MeetingTurn:
        await self.session.flush()
        return turn

    async def get_turns(self, meeting_id: uuid.UUID) -> list[MeetingTurn]:
        result = await self.session.execute(
            select(MeetingTurn).where(MeetingTurn.meeting_id == meeting_id).order_by(MeetingTurn.turn_number)
        )
        return list(result.scalars().all())

    async def add_statement(self, meeting_id: uuid.UUID, speaker_agent_id: uuid.UUID, content: str, turn_id: uuid.UUID | None = None, statement_type: str = "general", reply_to_id: uuid.UUID | None = None, token_count: int | None = None) -> MeetingStatement:
        s = MeetingStatement(
            meeting_id=meeting_id, speaker_agent_id=speaker_agent_id, content=content,
            turn_id=turn_id, statement_type=statement_type, reply_to_statement_id=reply_to_id,
            token_count=token_count,
        )
        self.session.add(s)
        await self.session.flush()
        return s

    async def get_statements(self, meeting_id: uuid.UUID) -> list[MeetingStatement]:
        result = await self.session.execute(
            select(MeetingStatement).where(MeetingStatement.meeting_id == meeting_id).order_by(MeetingStatement.created_at)
        )
        return list(result.scalars().all())

    async def get_recent_statements(self, meeting_id: uuid.UUID, count: int = 5) -> list[MeetingStatement]:
        result = await self.session.execute(
            select(MeetingStatement).where(MeetingStatement.meeting_id == meeting_id).order_by(MeetingStatement.created_at.desc()).limit(count)
        )
        return list(reversed(result.scalars().all()))

    async def save_minutes(self, meeting_id: uuid.UUID, content: str, summary: str, action_items: list, decisions: list, generated_by: uuid.UUID, approved_by: uuid.UUID | None = None) -> MeetingMinutes:
        # meeting_id 是唯一键而非主键，必须按列查询才能找到已有纪要
        existing = await self.get_minutes(meeting_id)
        if existing:
            existing.content = content
            existing.summary = summary
            existing.action_items = action_items
            existing.decisions = decisions
            existing.approved_by = approved_by
            existing.version += 1
            await self.session.flush()
            return existing
        m = MeetingMinutes(
            meeting_id=meeting_id, content=content, summary=summary,
            action_items=action_items, decisions=decisions,
            generated_by_agent_id=generated_by, approved_by=approved_by,
        )
        self.session.add(m)
        await self.session.flush()
        return m

    async def get_minutes(self, meeting_id: uuid.UUID) -> MeetingMinutes | None:
        result = await self.session.execute(select(MeetingMinutes).where(MeetingMinutes.meeting_id == meeting_id))
        return result.scalar_one_or_none()
