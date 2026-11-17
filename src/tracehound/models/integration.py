"""`integrations`: telemetry backends a user connects, one per kind per user.

The credential is AES-GCM encrypted by the backend before it reaches this table.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    LargeBinary,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from tracehound.models.base import Base, Timestamps


class Integration(Timestamps, Base):
    __tablename__ = "integrations"
    __table_args__ = (
        CheckConstraint("kind in ('loki', 'prometheus', 'tempo', 'github')"),
        CheckConstraint("status in ('untested', 'active', 'failing')"),
        CheckConstraint("jsonb_typeof(config) = 'object'"),
        CheckConstraint("(secret_ciphertext is null) = (secret_key_version is null)"),
        UniqueConstraint("user_id", "kind"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    user_id: Mapped[UUID] = mapped_column(ForeignKey("auth.users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(Text)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    secret_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    secret_key_version: Mapped[int | None] = mapped_column(SmallInteger)
    status: Mapped[str] = mapped_column(Text, server_default="untested")
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
