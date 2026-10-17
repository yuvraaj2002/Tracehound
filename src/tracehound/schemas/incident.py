"""Incident contracts shared across layers."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentCreateRequest(BaseModel):
    """Payload for ``POST /v1/incidents``."""

    model_config = ConfigDict(extra="forbid")

    service_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._-]+$")
    symptom: str = Field(min_length=1, max_length=2000)
    window_start: AwareDatetime
    window_end: AwareDatetime
    severity: Severity
    trace_id: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("window_start", "window_end")
    @classmethod
    def _to_utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def _window_is_ordered(self) -> Self:
        if self.window_end <= self.window_start:
            raise ValueError("window_end must be after window_start")
        return self


class IncidentAccepted(BaseModel):
    """Response for an accepted investigation request."""

    incident_id: UUID
    run_id: UUID
    status_url: str
