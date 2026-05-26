import uuid
from dataclasses import dataclass, field
from enum import StrEnum, IntEnum


class MeetingType(StrEnum):
    COORDINATION = "coordination"
    USER_DIRECT = "user_direct"
    RECRUITMENT_REVIEW = "recruitment_review"
    EMERGENCY = "emergency"
    DAILY_STANDUP = "daily_standup"
    AD_HOC = "ad_hoc"


class MeetingStatus(StrEnum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    ADJOURNED = "adjourned"
    CANCELLED = "cancelled"
    MINUTES_PENDING = "minutes_pending"
    COMPLETED = "completed"


class TurnType(StrEnum):
    STATEMENT = "statement"
    QUESTION = "question"
    ANSWER = "answer"
    PROPOSAL = "proposal"
    DECISION = "decision"
    HANDOFF = "handoff"
    REQUEST_TO_SPEAK_ACK = "request_to_speak_ack"
    POLL_RESPONSE = "poll_response"


class StatementType(StrEnum):
    GENERAL = "general"
    REQUEST_TO_SPEAK = "request_to_speak"
    ACKNOWLEDGMENT = "acknowledgment"
    MOTION = "motion"
    VOTE = "vote"
    MINUTES_DRAFT = "minutes_draft"
    DECISION = "decision"
    POLL_QUERY = "poll_query"
    POLL_RESPONSE = "poll_response"


# Valid transition map for meeting state
MEETING_TRANSITIONS: dict[MeetingStatus, set[MeetingStatus]] = {
    MeetingStatus.SCHEDULED: {MeetingStatus.IN_PROGRESS, MeetingStatus.CANCELLED},
    MeetingStatus.IN_PROGRESS: {MeetingStatus.ADJOURNED, MeetingStatus.CANCELLED},
    MeetingStatus.ADJOURNED: {MeetingStatus.MINUTES_PENDING, MeetingStatus.COMPLETED},
    MeetingStatus.MINUTES_PENDING: {MeetingStatus.COMPLETED},
    MeetingStatus.CANCELLED: set(),
    MeetingStatus.COMPLETED: set(),
}
