"""Canonical trace records as the trace tools return them."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator


class Span(BaseModel):
    """One span of a distributed trace. ``parent_span_id`` is None for the root span."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    trace_id: str
    span_id: str
    parent_span_id: str | None
    service: str
    name: str
    start: AwareDatetime
    duration_ms: float = Field(ge=0)
    status: Literal["ok", "error"]
    error: str | None = None

    @field_validator("start")
    @classmethod
    def _to_utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)
