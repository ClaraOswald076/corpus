import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, UniqueConstraint, CheckConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
import sqlalchemy as sa

from src.models.base import Base, TimestampMixin, UUIDMixin, utcnow


class Meeting(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "meetings"

    meeting_code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    meeting_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    agenda: Mapped[str | None] = mapped_column(Text, nullable=True)
    chair_agent_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, ForeignKey("agents.id"), nullable=True)
    secretary_agent_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, ForeignKey("agents.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="scheduled", nullable=False)
    max_turns: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    max_duration_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    stalemate_threshold: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    meeting_context: Mapped[dict] = mapped_column(sa.JSON, default=dict, nullable=False)
    parent_meeting_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, ForeignKey("meetings.id"), nullable=True)
    task_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, ForeignKey("tasks.id"), nullable=True)

    chair_agent = relationship("Agent", foreign_keys=[chair_agent_id])
    secretary_agent = relationship("Agent", foreign_keys=[secretary_agent_id])
    participants: Mapped[list["MeetingParticipant"]] = relationship("MeetingParticipant", back_populates="meeting", cascade="all, delete-orphan")
    turns: Mapped[list["MeetingTurn"]] = relationship("MeetingTurn", back_populates="meeting", cascade="all, delete-orphan")
    statements: Mapped[list["MeetingStatement"]] = relationship("MeetingStatement", back_populates="meeting", cascade="all, delete-orphan")
    minutes: Mapped["MeetingMinutes | None"] = relationship("MeetingMinutes", back_populates="meeting", uselist=False)

    __table_args__ = (
        CheckConstraint("meeting_type IN ('coordination','user_direct','recruitment_review','emergency','daily_standup','ad_hoc')", name="ck_meeting_type"),
        CheckConstraint("status IN ('scheduled','in_progress','adjourned','cancelled','minutes_pending','completed')", name="ck_meeting_status"),
    )


class MeetingParticipant(Base, UUIDMixin):
    __tablename__ = "meeting_participants"

    meeting_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False)
    agent_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, ForeignKey("agents.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="participant", nullable=False)
    is_required: Mapped[bool] = mapped_column(default=False, nullable=False)
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    meeting = relationship("Meeting", back_populates="participants")

    __table_args__ = (
        UniqueConstraint("meeting_id", "agent_id"),
        CheckConstraint("role IN ('chair','secretary','participant','observer')", name="ck_participant_role"),
    )


class MeetingTurn(Base, UUIDMixin):
    __tablename__ = "meeting_turns"

    meeting_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False)
    turn_number: Mapped[int] = mapped_column(Integer, nullable=False)
    speaker_agent_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, ForeignKey("agents.id"), nullable=False)
    turn_type: Mapped[str] = mapped_column(String(50), default="statement", nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    meeting = relationship("Meeting", back_populates="turns")

    __table_args__ = (
        UniqueConstraint("meeting_id", "turn_number"),
        CheckConstraint("turn_type IN ('statement','question','answer','proposal','decision','handoff','request_to_speak_ack','poll_response')", name="ck_turn_type"),
        CheckConstraint("status IN ('pending','speaking','completed','interrupted','timed_out')", name="ck_turn_status"),
    )


class MeetingStatement(Base, UUIDMixin):
    __tablename__ = "meeting_statements"

    meeting_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False)
    turn_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, ForeignKey("meeting_turns.id"), nullable=True)
    speaker_agent_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, ForeignKey("agents.id"), nullable=False)
    statement_type: Mapped[str] = mapped_column(String(50), default="general", nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    reply_to_statement_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, ForeignKey("meeting_statements.id"), nullable=True)
    statement_metadata: Mapped[dict] = mapped_column("metadata", sa.JSON, default=dict, nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    meeting = relationship("Meeting", back_populates="statements")
    reply_to = relationship("MeetingStatement", remote_side="MeetingStatement.id")

    __table_args__ = (
        Index("idx_meeting_statements_meeting", "meeting_id", "created_at"),
        CheckConstraint("statement_type IN ('general','request_to_speak','acknowledgment','motion','vote','minutes_draft','decision','poll_query','poll_response')", name="ck_statement_type"),
    )


class MeetingMinutes(Base, UUIDMixin):
    __tablename__ = "meeting_minutes"

    meeting_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, ForeignKey("meetings.id"), unique=True, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_items: Mapped[list] = mapped_column(sa.JSON, default=list, nullable=False)
    decisions: Mapped[list] = mapped_column(sa.JSON, default=list, nullable=False)
    generated_by_agent_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, ForeignKey("agents.id"), nullable=False)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, ForeignKey("agents.id"), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    meeting = relationship("Meeting", back_populates="minutes")
