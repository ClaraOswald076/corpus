import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum


class MessageType(StrEnum):
    STATEMENT = "statement"
    CONTROL = "control"
    REQUEST_TO_SPEAK = "request_to_speak"
    TURN_GRANTED = "turn_granted"
    TURN_COMPLETE = "turn_complete"
    POLL_QUERY = "poll_query"
    POLL_RESPONSE = "poll_response"
    CHAIR_ANNOUNCEMENT = "chair_announcement"
    SECRETARY_SUMMARY = "secretary_summary"
    MEETING_ADJOURNED = "meeting_adjourned"


@dataclass
class MeetingMessage:
    message_type: MessageType
    sender_agent_id: uuid.UUID
    content: str = ""
    meeting_id: uuid.UUID | None = None
    turn_number: int = 0
    reply_to_message_id: str | None = None
    metadata: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))


class MeetingMessageBus:
    def __init__(self, meeting_id: uuid.UUID):
        self.meeting_id = meeting_id
        self._queues: dict[uuid.UUID, asyncio.Queue[MeetingMessage]] = {}
        self._history: list[MeetingMessage] = []
        self._lock = asyncio.Lock()

    async def subscribe(self, agent_id: uuid.UUID) -> asyncio.Queue[MeetingMessage]:
        async with self._lock:
            if agent_id not in self._queues:
                self._queues[agent_id] = asyncio.Queue()
                # Send history to late-joining agent
                for msg in self._history[-50:]:
                    await self._queues[agent_id].put(msg)
            return self._queues[agent_id]

    def has_subscriber(self, agent_id: uuid.UUID) -> bool:
        return agent_id in self._queues

    async def unsubscribe(self, agent_id: uuid.UUID):
        async with self._lock:
            self._queues.pop(agent_id, None)

    async def publish(self, message: MeetingMessage):
        message.meeting_id = self.meeting_id
        self._history.append(message)
        # Keep history bounded
        if len(self._history) > 500:
            self._history = self._history[-200:]
        async with self._lock:
            for agent_id, queue in self._queues.items():
                await queue.put(message)

    async def broadcast_control(self, sender_id: uuid.UUID, content: str, announcement_type: MessageType = MessageType.CHAIR_ANNOUNCEMENT):
        await self.publish(MeetingMessage(
            message_type=announcement_type,
            sender_agent_id=sender_id,
            content=content,
        ))

    def get_history(self) -> list[MeetingMessage]:
        return list(self._history)

    def get_recent(self, count: int = 10) -> list[MeetingMessage]:
        return self._history[-count:]

    @property
    def subscriber_count(self) -> int:
        return len(self._queues)

    @property
    def message_count(self) -> int:
        return len(self._history)


class MessageBusRegistry:
    def __init__(self):
        self._buses: dict[uuid.UUID, MeetingMessageBus] = {}
        self._lock = asyncio.Lock()

    async def create_bus(self, meeting_id: uuid.UUID) -> MeetingMessageBus:
        async with self._lock:
            if meeting_id in self._buses:
                return self._buses[meeting_id]
            bus = MeetingMessageBus(meeting_id)
            self._buses[meeting_id] = bus
            return bus

    def get_bus(self, meeting_id: uuid.UUID) -> MeetingMessageBus | None:
        return self._buses.get(meeting_id)

    async def remove_bus(self, meeting_id: uuid.UUID):
        async with self._lock:
            self._buses.pop(meeting_id, None)

    @property
    def active_meetings(self) -> int:
        return len(self._buses)


message_bus_registry = MessageBusRegistry()
