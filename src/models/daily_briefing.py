import uuid
from datetime import date, datetime
from sqlalchemy import String, Integer, Text, Date, DateTime, ForeignKey, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
import sqlalchemy as sa

from src.models.base import Base, TimestampMixin, UUIDMixin, utcnow


class DailyBriefing(Base, UUIDMixin):
    __tablename__ = "daily_briefings"

    briefing_date: Mapped[date] = mapped_column(Date, unique=True, nullable=False)
    generated_by: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, ForeignKey("agents.id"), nullable=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, ForeignKey("agents.id"), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="draft", nullable=False)
    email_sent_to: Mapped[str | None] = mapped_column(String(500), nullable=True)
    email_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('draft','reviewed','sent','failed')", name="ck_briefing_status"),
    )
