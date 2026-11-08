"""Canonical log records as the log tools return them."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue, field_validator


class LogLine(BaseModel):
    """One structured log record."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    timestamp: AwareDatetime
    service: str
    level: Literal["DEBUG", "INFO", "WARN", "ERROR"]
    message: str
    trace_id: str | None
    attributes: dict[str, JsonValue] = Field(default_factory=dict)
    occurrence: int = Field(default=1, ge=1, description="How many times this message appeared")

    @field_validator("timestamp")
    @classmethod
    def _to_utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)
