import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
import sqlalchemy as sa

from src.models.base import Base, TimestampMixin, UUIDMixin, utcnow


class EscalationEvent(Base, UUIDMixin):
    __tablename__ = "escalation_events"

    task_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, ForeignKey("tasks.id"), nullable=False)
    from_agent_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, ForeignKey("agents.id"), nullable=False)
    from_department_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, ForeignKey("departments.id"), nullable=False)
    to_agent_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, ForeignKey("agents.id"), nullable=False)
    to_department_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, ForeignKey("departments.id"), nullable=False)
    escalation_level: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    task_context: Mapped[dict | None] = mapped_column(sa.JSON, nullable=True)
    resolution: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_by_agent_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, ForeignKey("agents.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "resolution IN ('pending','modify_and_retry','escalate_higher','resolve_directly','return_to_originator','cancelled')",
            name="ck_escalation_resolution",
        ),
    )
