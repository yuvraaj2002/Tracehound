"""Incident contracts shared across layers."""

from datetime import UTC, date, datetime, timedelta
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


class IncidentRecord(BaseModel):
    """A stored incident, as returned by ``GET /v1/incidents``."""

    id: UUID
    run_id: UUID
    service_id: str
    symptom: str
    severity: Severity
    window_start: AwareDatetime
    window_end: AwareDatetime
    trace_id: str | None
    state: str
    created_at: AwareDatetime
    updated_at: AwareDatetime


MAX_STATS_RANGE = timedelta(days=366)


class IncidentStatsQuery(BaseModel):
    """Query for ``GET /v1/incidents/stats``: the half-open range ``[from, to)``."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_: AwareDatetime = Field(alias="from")
    to: AwareDatetime

    @field_validator("from_", "to")
    @classmethod
    def _to_utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def _range_is_valid(self) -> Self:
        if self.to <= self.from_:
            raise ValueError("to must be after from")
        if self.to - self.from_ > MAX_STATS_RANGE:
            raise ValueError(f"range must be at most {MAX_STATS_RANGE.days} days")
        return self


class IncidentListQuery(IncidentStatsQuery):
    """Query for ``GET /v1/incidents``: one page of the range ``[from, to)``, newest first."""

    cursor: str | None = None
    limit: int = Field(default=20, ge=1, le=100)


class IncidentPage(BaseModel):
    """Response for ``GET /v1/incidents``. Pass `next_cursor` back as `cursor` for the next page."""

    items: list[IncidentRecord]
    next_cursor: str | None = None


class SeverityCounts(BaseModel):
    low: int
    medium: int
    high: int
    critical: int


class ServiceCount(BaseModel):
    service_id: str
    count: int


class IncidentStatsPoint(SeverityCounts):
    """Incidents created on one UTC day (clipped to the requested range)."""

    day: date
    total: int


class IncidentStats(BaseModel):
    """Response for ``GET /v1/incidents/stats``. Everything is bucketed on ``created_at``."""

    from_: AwareDatetime = Field(serialization_alias="from")
    to: AwareDatetime
    total: int
    previous_total: int = Field(
        description="Incidents in the equal-length period immediately before `from`."
    )
    by_severity: SeverityCounts
    by_state: dict[str, int]
    top_services: list[ServiceCount] = Field(description="Up to 5, busiest first.")
    timeseries: list[IncidentStatsPoint] = Field(description="One point per UTC day, zero-filled.")
    avg_window_seconds: float | None = Field(description="Null when there are no incidents.")
    trace_coverage: float | None = Field(
        description="Fraction of incidents with a trace_id; null when there are none."
    )
