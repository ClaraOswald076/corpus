import uuid
import sqlalchemy as sa
from sqlalchemy import String, Integer, Boolean, Text, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin, UUIDMixin


class Department(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "departments"

    parent_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    org_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    tier: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    dept_type: Mapped[str] = mapped_column(String(50), nullable=False)
    dept_code: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True)
    head_agent_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    parent = relationship("Department", remote_side="Department.id", backref="children")
    agents: Mapped[list["Agent"]] = relationship("Agent", back_populates="department", foreign_keys="Agent.department_id")


class Agent(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "agents"

    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    role: Mapped[str] = mapped_column(String(255), nullable=False)
    department_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, ForeignKey("departments.id"), nullable=False)
    reports_to_agent_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, ForeignKey("agents.id"), nullable=True)
    model_preset_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, ForeignKey("model_presets.id"), nullable=True)
    agent_folder_path: Mapped[str] = mapped_column(String(1000), unique=True, nullable=False)
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    temperature: Mapped[float] = mapped_column(default=0.7, nullable=False)
    max_tokens: Mapped[int] = mapped_column(Integer, default=4096, nullable=False)
    max_memory_tokens: Mapped[int] = mapped_column(Integer, default=100000, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    availability_status: Mapped[str] = mapped_column(String(50), default="available", nullable=False)

    department = relationship("Department", back_populates="agents", foreign_keys=[department_id])
    reports_to = relationship("Agent", remote_side="Agent.id", backref="subordinates")
    model_preset = relationship("ModelPreset", back_populates="agents")
    soul_document: Mapped["SoulDocument | None"] = relationship("SoulDocument", back_populates="agent", uselist=False)

    __table_args__ = (
        Index("idx_agents_department", "department_id"),
        Index("idx_agents_status", "is_active"),
    )


class AgentDepartmentAssignment(Base, UUIDMixin):
    __tablename__ = "agent_department_assignments"

    agent_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
    department_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, ForeignKey("departments.id", ondelete="CASCADE"), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (
        UniqueConstraint("agent_id", "department_id"),
    )
