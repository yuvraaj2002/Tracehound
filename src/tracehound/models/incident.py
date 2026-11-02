"""`incidents`: incident intake records, one per reported incident."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column

from tracehound.models.base import Base, Timestamps


class Incident(Timestamps, Base):
    __tablename__ = "incidents"
    __table_args__ = (
        CheckConstraint("severity in ('low', 'medium', 'high', 'critical')"),
        CheckConstraint("window_end > window_start"),
        CheckConstraint("state in ('CREATED', 'RUNNING', 'COMPLETED', 'FAILED')"),
        Index("incidents_user_id_idx", "user_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    run_id: Mapped[UUID]
    user_id: Mapped[UUID] = mapped_column(ForeignKey("auth.users.id", ondelete="CASCADE"))
    service_id: Mapped[str] = mapped_column(Text)
    symptom: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(Text)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    trace_id: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text, server_default="CREATED")
