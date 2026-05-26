import uuid
from datetime import date, datetime
from sqlalchemy import String, Integer, Text, Float, Date, DateTime, ForeignKey, Boolean, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
import sqlalchemy as sa

from src.models.base import Base, TimestampMixin, UUIDMixin, utcnow


class AuditLog(Base, UUIDMixin):
    __tablename__ = "audit_log"

    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(500), nullable=False)
    details: Mapped[dict] = mapped_column(sa.JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        Index("idx_audit_entity", "entity_type", "entity_id"),
        Index("idx_audit_created", "created_at"),
        Index("idx_audit_event_type", "event_type"),
    )


class LLMCallRecord(Base, UUIDMixin):
    __tablename__ = "llm_call_records"

    agent_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, ForeignKey("agents.id"), nullable=True)
    preset_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, ForeignKey("model_presets.id"), nullable=True)
    task_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, ForeignKey("tasks.id"), nullable=True)
    meeting_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, ForeignKey("meetings.id"), nullable=True)
    call_type: Mapped[str] = mapped_column(String(50), nullable=False)
    model_string: Mapped[str] = mapped_column(String(500), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    semantic_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        Index("idx_llm_calls_agent", "agent_id", "created_at"),
        Index("idx_llm_calls_task", "task_id"),
        Index("idx_llm_calls_meeting", "meeting_id"),
        Index("idx_llm_calls_hash", "semantic_hash"),
    )


class CostRecord(Base, UUIDMixin):
    __tablename__ = "cost_records"

    date: Mapped[date] = mapped_column(Date, nullable=False)
    agent_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, ForeignKey("agents.id"), nullable=True)
    department_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, ForeignKey("departments.id"), nullable=True)
    preset_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, ForeignKey("model_presets.id"), nullable=True)
    total_calls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_prompt_tokens: Mapped[int] = mapped_column(sa.BigInteger, default=0, nullable=False)
    total_completion_tokens: Mapped[int] = mapped_column(sa.BigInteger, default=0, nullable=False)
    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("date", "agent_id", "preset_id"),
    )


class AgentRuntimeMetric(Base, UUIDMixin):
    __tablename__ = "agent_runtime_metrics"

    agent_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, ForeignKey("agents.id"), nullable=False)
    metric_name: Mapped[str] = mapped_column(String(100), nullable=False)
    metric_value: Mapped[float] = mapped_column(Float, nullable=False)
    period: Mapped[str] = mapped_column(String(20), default="daily", nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        Index("idx_agent_metrics_lookup", "agent_id", "metric_name", "period_start"),
    )
