"""`investigation_results`: what a run produced for an incident, one row per incident."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from tracehound.models.base import Base, Timestamps


class InvestigationResultRow(Timestamps, Base):
    """Named `...Row` so it doesn't clash with the `InvestigationResult` API schema."""

    __tablename__ = "investigation_results"
    __table_args__ = (Index("investigation_results_user_id_idx", "user_id"),)

    incident_id: Mapped[UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("auth.users.id", ondelete="CASCADE"))
    run_id: Mapped[UUID]
    scope: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    findings: Mapped[list[Any]] = mapped_column(JSONB, server_default=text("'[]'"))
    evidence: Mapped[list[Any]] = mapped_column(JSONB, server_default=text("'[]'"))
    hypotheses: Mapped[list[Any]] = mapped_column(JSONB, server_default=text("'[]'"))
    agent_runs: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'"))
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
