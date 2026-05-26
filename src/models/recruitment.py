import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
import sqlalchemy as sa

from src.models.base import Base, TimestampMixin, UUIDMixin, utcnow


class RecruitmentRequest(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "recruitment_requests"

    request_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    requester_agent_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, ForeignKey("agents.id"), nullable=True)
    requester_user_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    target_department_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, ForeignKey("departments.id"), nullable=False)
    target_tier: Mapped[int] = mapped_column(Integer, nullable=False)
    proposed_role: Mapped[str] = mapped_column(String(200), nullable=False)
    proposed_capabilities: Mapped[dict] = mapped_column(sa.JSON, default=dict, nullable=False)
    reason_category: Mapped[str] = mapped_column(String(50), nullable=False)
    reason_detail: Mapped[str] = mapped_column(Text, nullable=False)
    workload_evidence: Mapped[dict | None] = mapped_column(sa.JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="drafted", nullable=False)
    hr_reviewer_agent_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, ForeignKey("agents.id"), nullable=True)
    hr_decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "reason_category IN ('workload','tech_gap','new_capability','replacement')",
            name="ck_recruitment_reason",
        ),
        CheckConstraint(
            "status IN ('drafted','hr_reviewing','approved','rejected','returned','meeting_scheduled','meeting_in_progress','soul_finalized','agent_created','onboarding','active','closed')",
            name="ck_recruitment_status",
        ),
    )


class RecruitmentMeeting(Base, UUIDMixin):
    __tablename__ = "recruitment_meetings"

    recruitment_request_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, ForeignKey("recruitment_requests.id"), nullable=False)
    meeting_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, ForeignKey("meetings.id"), nullable=False)
    meeting_type: Mapped[str] = mapped_column(String(50), default="recruitment_review", nullable=False)
    soul_md_draft: Mapped[str | None] = mapped_column(Text, nullable=True)
    soul_md_final: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
