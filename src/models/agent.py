import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Boolean, Text, Float, DateTime, ForeignKey, LargeBinary
from sqlalchemy.orm import Mapped, mapped_column, relationship
import sqlalchemy as sa

from src.models.base import Base, TimestampMixin, UUIDMixin


class ModelPreset(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "model_presets"

    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    litellm_model_string: Mapped[str] = mapped_column(String(500), nullable=False)
    default_params: Mapped[dict] = mapped_column(sa.JSON, default=dict, nullable=False)
    cost_per_1k_input: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    cost_per_1k_output: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    retry_delay_sec: Mapped[float] = mapped_column(Float, default=2.0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    api_keys: Mapped[list["ApiKey"]] = relationship("ApiKey", back_populates="preset", cascade="all, delete-orphan")
    agents: Mapped[list["Agent"]] = relationship("Agent", back_populates="model_preset")


class ApiKey(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "api_keys"

    preset_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, ForeignKey("model_presets.id", ondelete="CASCADE"), nullable=False)
    key_label: Mapped[str] = mapped_column(String(255), nullable=False)
    encrypted_key: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    key_prefix: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    preset = relationship("ModelPreset", back_populates="api_keys")


class SoulDocument(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "soul_documents"

    agent_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, ForeignKey("agents.id", ondelete="CASCADE"), unique=True, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    file_last_modified: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_edited_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    agent = relationship("Agent", back_populates="soul_document")


class MemoryDocument(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "memory_documents"

    agent_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
    entry_type: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    importance: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    access_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_accessed: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
