"""`agent_model_settings`: the model each investigation agent runs on, one row per user."""

from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from tracehound.models.base import Base, Timestamps


class AgentModelSettingsRow(Timestamps, Base):
    __tablename__ = "agent_model_settings"
    __table_args__ = (CheckConstraint("jsonb_typeof(config) = 'object'"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("auth.users.id", ondelete="CASCADE"), unique=True
    )
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
