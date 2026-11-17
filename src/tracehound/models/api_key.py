"""`api_keys`: keys issued to users. Only an HMAC of each raw key is stored."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from tracehound.models.base import Base, Timestamps


class ApiKey(Timestamps, Base):
    __tablename__ = "api_keys"
    __table_args__ = (
        CheckConstraint("length(name) between 1 and 100"),
        Index("api_keys_user_id_idx", "user_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    user_id: Mapped[UUID] = mapped_column(ForeignKey("auth.users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(Text)
    hash: Mapped[str] = mapped_column(Text, unique=True)
    prefix: Mapped[str] = mapped_column(Text)
    suffix: Mapped[str] = mapped_column(Text)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
