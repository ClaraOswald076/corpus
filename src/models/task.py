import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Text, Float, DateTime, ForeignKey, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
import sqlalchemy as sa

from src.models.base import Base, TimestampMixin, UUIDMixin


class Task(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "tasks"

    task_code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    parent_task_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, ForeignKey("tasks.id"), nullable=True)
    root_task_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, ForeignKey("tasks.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    priority: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)
    assigned_agent_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, ForeignKey("agents.id"), nullable=True)
    assigned_department_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, ForeignKey("departments.id"), nullable=True)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    creator_agent_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, ForeignKey("agents.id"), nullable=True)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    timeout_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_effort_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_effort_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    escalation_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    context_snapshot: Mapped[dict | None] = mapped_column(sa.JSON, nullable=True)
    tags: Mapped[list] = mapped_column(sa.JSON, default=list, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    parent_task = relationship("Task", remote_side="Task.id", backref="sub_tasks", foreign_keys=[parent_task_id])
    root_task = relationship("Task", remote_side="Task.id", foreign_keys=[root_task_id])
    assigned_agent = relationship("Agent", foreign_keys=[assigned_agent_id])
    assigned_department = relationship("Department", foreign_keys=[assigned_department_id])
    creator_agent = relationship("Agent", foreign_keys=[creator_agent_id])
    artifacts: Mapped[list["TaskArtifact"]] = relationship("TaskArtifact", back_populates="task", cascade="all, delete-orphan")
    dependencies: Mapped[list["TaskDependency"]] = relationship("TaskDependency", foreign_keys="TaskDependency.task_id", back_populates="task", cascade="all, delete-orphan")
    dependents: Mapped[list["TaskDependency"]] = relationship("TaskDependency", foreign_keys="TaskDependency.depends_on_task_id", back_populates="depends_on_task", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("status IN ('pending','in_progress','completed','failed','needs_clarification','cancelled','blocked')", name="ck_task_status"),
        CheckConstraint("priority IN ('critical','high','medium','low')", name="ck_task_priority"),
    )


class TaskDependency(Base, UUIDMixin):
    __tablename__ = "task_dependencies"

    task_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    depends_on_task_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    dependency_type: Mapped[str] = mapped_column(String(50), default="blocks", nullable=False)

    task = relationship("Task", foreign_keys=[task_id], back_populates="dependencies")
    depends_on_task = relationship("Task", foreign_keys=[depends_on_task_id], back_populates="dependents")

    __table_args__ = (
        UniqueConstraint("task_id", "depends_on_task_id"),
    )


class TaskArtifact(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "task_artifacts"

    task_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    artifact_type: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    produced_by_agent_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, ForeignKey("agents.id"), nullable=True)

    task = relationship("Task", back_populates="artifacts")
