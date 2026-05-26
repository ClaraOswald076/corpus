import uuid
import time
from dataclasses import dataclass, field


@dataclass
class RequestToSpeak:
    agent_id: uuid.UUID
    agent_name: str
    urgency: int = 0       # 0-10
    topic_relevance: float = 0.0  # 0.0-1.0
    reference_to_prior: str = ""  # 引用的先前发言
    request_time: float = field(default_factory=time.time)

    @property
    def priority_score(self) -> float:
        # urgency dominates, then direct reference, then relevance, then time
        ref_bonus = 1.0 if self.reference_to_prior else 0.0
        time_penalty = min((time.time() - self.request_time) / 60.0, 1.0) * 0.5
        return (self.urgency * 10.0) + ref_bonus * 5.0 + (self.topic_relevance * 3.0) + time_penalty


class SpeakerQueue:
    def __init__(self):
        self._requests: list[RequestToSpeak] = []
        self._spoken_agents: set[uuid.UUID] = set()

    def submit(self, request: RequestToSpeak):
        # Replace if same agent already in queue
        self._requests = [r for r in self._requests if r.agent_id != request.agent_id]
        self._requests.append(request)

    def withdraw(self, agent_id: uuid.UUID):
        self._requests = [r for r in self._requests if r.agent_id != agent_id]

    def mark_spoken(self, agent_id: uuid.UUID):
        self._spoken_agents.add(agent_id)
        self.withdraw(agent_id)

    def get_next(self) -> RequestToSpeak | None:
        if not self._requests:
            return None
        self._requests.sort(key=lambda r: r.priority_score, reverse=True)
        return self._requests[0]

    def get_all_pending(self) -> list[RequestToSpeak]:
        return sorted(self._requests, key=lambda r: r.priority_score, reverse=True)

    def has_unspoken(self, agent_ids: set[uuid.UUID]) -> list[uuid.UUID]:
        """Return agents who haven't spoken yet"""
        return [aid for aid in agent_ids if aid not in self._spoken_agents]

    def clear(self):
        self._requests.clear()

    @property
    def pending_count(self) -> int:
        return len(self._requests)

    @property
    def spoken_count(self) -> int:
        return len(self._spoken_agents)

    def reset_spoken(self):
        self._spoken_agents.clear()
