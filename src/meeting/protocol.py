import uuid
import asyncio
import hashlib
from datetime import datetime, timezone
from src.meeting.types import MeetingType, MeetingStatus, TurnType, StatementType, MEETING_TRANSITIONS
from src.meeting.message_bus import MeetingMessageBus, MeetingMessage, MessageType, message_bus_registry
from src.meeting.speaker_queue import SpeakerQueue, RequestToSpeak
from src.core.config import settings
from src.core.exceptions import MissingSecretariatError


class MeetingProtocolEngine:
    def __init__(self, meeting_id: uuid.UUID, meeting_type: MeetingType, chair_agent_id: uuid.UUID | None, secretary_agent_id: uuid.UUID):
        self.meeting_id = meeting_id
        self.meeting_type = meeting_type
        self.chair_agent_id = chair_agent_id
        self.secretary_agent_id = secretary_agent_id
        self.status = MeetingStatus.SCHEDULED
        self.turn_count = 0
        self.max_turns = settings.meeting_max_turns_default
        self.stalemate_threshold = settings.meeting_stalemate_consecutive_rounds
        self.participant_ids: set[uuid.UUID] = set()
        self.speaker_queue = SpeakerQueue()
        self.bus: MeetingMessageBus | None = None
        self._content_history: list[str] = []
        self._task: asyncio.Task | None = None

    async def start(self):
        if self.secretary_agent_id not in self.participant_ids:
            raise MissingSecretariatError("秘书科Agent必须参会")
        self.bus = await message_bus_registry.create_bus(self.meeting_id)
        self.status = MeetingStatus.IN_PROGRESS
        for pid in self.participant_ids:
            await self.bus.subscribe(pid)
        await self.bus.broadcast_control(
            self.chair_agent_id or self.secretary_agent_id,
            f"会议开始。类型: {self.meeting_type.value}",
        )

    async def adjourn(self) -> bool:
        """Run pre-termination poll, return True if all confirmed"""
        if not self.bus:
            return True
        # Poll all participants
        all_confirmed = True
        for pid in self.participant_ids:
            if pid == self.chair_agent_id:
                continue
            poll_msg = MeetingMessage(
                message_type=MessageType.POLL_QUERY,
                sender_agent_id=self.chair_agent_id or self.secretary_agent_id,
                content=f"是否还有补充意见？",
                metadata={"target_agent_id": str(pid)},
            )
            await self.bus.publish(poll_msg)
            # Wait for response
            queue = await self.bus.subscribe(pid)
            try:
                response = await asyncio.wait_for(
                    self._wait_for_poll_response(queue, pid),
                    timeout=settings.meeting_poll_timeout_per_agent_seconds,
                )
                if response and "有补充" in response:
                    all_confirmed = False
            except asyncio.TimeoutError:
                pass  # Treat timeout as "no supplement"

        self.status = MeetingStatus.ADJOURNED
        if all_confirmed:
            await self.bus.broadcast_control(
                self.chair_agent_id or self.secretary_agent_id,
                "全体无补充，会议休会。",
                MessageType.MEETING_ADJOURNED,
            )
        return all_confirmed

    async def _wait_for_poll_response(self, queue: asyncio.Queue, agent_id: uuid.UUID) -> str | None:
        while True:
            msg = await queue.get()
            if msg.message_type == MessageType.POLL_RESPONSE and msg.sender_agent_id == agent_id:
                return msg.content
            if msg.message_type == MessageType.MEETING_ADJOURNED:
                return None

    async def submit_request_to_speak(self, agent_id: uuid.UUID, agent_name: str, urgency: int = 5, topic_relevance: float = 0.5, reference: str = ""):
        request = RequestToSpeak(
            agent_id=agent_id, agent_name=agent_name,
            urgency=urgency, topic_relevance=topic_relevance, reference_to_prior=reference,
        )
        self.speaker_queue.submit(request)
        if self.bus:
            await self.bus.publish(MeetingMessage(
                message_type=MessageType.REQUEST_TO_SPEAK,
                sender_agent_id=agent_id,
                content=f"{agent_name} 请求发言",
                metadata={"urgency": urgency, "topic_relevance": topic_relevance},
            ))

    async def grant_next_speaker(self) -> uuid.UUID | None:
        """Chair selects next speaker, returns agent_id or None"""
        next_request = self.speaker_queue.get_next()
        if not next_request:
            return None
        self.speaker_queue.mark_spoken(next_request.agent_id)
        self.turn_count += 1
        if self.bus:
            await self.bus.publish(MeetingMessage(
                message_type=MessageType.TURN_GRANTED,
                sender_agent_id=self.chair_agent_id or self.secretary_agent_id,
                content=f"请 {next_request.agent_name} 发言 (第{self.turn_count}轮)",
                turn_number=self.turn_count,
                metadata={"speaker_agent_id": str(next_request.agent_id)},
            ))
        return next_request.agent_id

    async def record_statement(self, speaker_id: uuid.UUID, content: str, statement_type: str = "general", token_count: int | None = None):
        """Record a statement and broadcast to all"""
        self._content_history.append(content)
        # Keep bounded
        if len(self._content_history) > 100:
            self._content_history = self._content_history[-50:]
        if self.bus:
            await self.bus.publish(MeetingMessage(
                message_type=MessageType.STATEMENT,
                sender_agent_id=speaker_id,
                content=content,
                turn_number=self.turn_count,
                metadata={"statement_type": statement_type, "token_count": token_count},
            ))

    async def chair_announce(self, content: str):
        if self.bus:
            await self.bus.broadcast_control(
                self.chair_agent_id or self.secretary_agent_id,
                content,
            )

    async def secretary_summary(self, content: str):
        if self.bus:
            await self.bus.publish(MeetingMessage(
                message_type=MessageType.SECRETARY_SUMMARY,
                sender_agent_id=self.secretary_agent_id,
                content=content,
            ))

    def check_stalemate(self) -> bool:
        """Check if recent rounds are too similar"""
        if len(self._content_history) < self.stalemate_threshold + 1:
            return False
        recent = self._content_history[-self.stalemate_threshold:]
        hashes = [hashlib.md5(c.encode()).hexdigest()[:8] for c in recent]
        # Simple check: if any hash repeats in recent rounds
        return len(set(hashes)) < len(hashes) - 1

    def should_continue(self) -> bool:
        """Determine if meeting should continue"""
        if self.turn_count >= self.max_turns:
            return False
        if self.check_stalemate():
            return False
        if self.turn_count > 0 and self.speaker_queue.pending_count == 0:
            return False
        return True

    def cancel(self):
        self.status = MeetingStatus.CANCELLED
        if self._task:
            self._task.cancel()

    def to_dict(self) -> dict:
        return {
            "meeting_id": str(self.meeting_id),
            "meeting_type": self.meeting_type.value,
            "status": self.status.value,
            "turn_count": self.turn_count,
            "pending_requests": self.speaker_queue.pending_count,
            "spoken_count": self.speaker_queue.spoken_count,
            "subscriber_count": self.bus.subscriber_count if self.bus else 0,
            "message_count": self.bus.message_count if self.bus else 0,
        }


class MeetingProtocolRegistry:
    def __init__(self):
        self._engines: dict[uuid.UUID, MeetingProtocolEngine] = {}

    def register(self, engine: MeetingProtocolEngine):
        self._engines[engine.meeting_id] = engine

    def get(self, meeting_id: uuid.UUID) -> MeetingProtocolEngine | None:
        return self._engines.get(meeting_id)

    def unregister(self, meeting_id: uuid.UUID):
        self._engines.pop(meeting_id, None)

    @property
    def active_count(self) -> int:
        return len(self._engines)


meeting_protocol_registry = MeetingProtocolRegistry()
