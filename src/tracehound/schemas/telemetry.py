"""Telemetry records as the read-only tools return them."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue, field_validator


class Deploy(BaseModel):
    """A deployment of one service version."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    service: str
    version: str
    previous_version: str | None
    deployed_at: AwareDatetime
    author: str
    commit: str
    change_summary: str
    config_diff: dict[str, dict[str, str | None]] = Field(
        default_factory=dict, description='Config key -> {"old": ..., "new": ...}'
    )

    @field_validator("deployed_at")
    @classmethod
    def _to_utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)


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

    @field_validator("timestamp")
    @classmethod
    def _to_utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)


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


class MetricPoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    timestamp: AwareDatetime
    value: float

    @field_validator("timestamp")
    @classmethod
    def _to_utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)


class MetricSeries(BaseModel):
    """One time series, such as checkout-api p95 latency, sampled every minute."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    service: str
    name: str
    unit: str
    points: list[MetricPoint]


class ServiceNode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    kind: str
    team: str


class Edge(BaseModel):
    """``source`` calls ``target``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: str
    target: str
    protocol: str


class Topology(BaseModel):
    """Service dependency graph."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    services: list[ServiceNode]
    edges: list[Edge]

    def neighbors(self, service: str) -> set[str]:
        """Services one hop away, in either direction."""
        return {e.target for e in self.edges if e.source == service} | {
            e.source for e in self.edges if e.target == service
        }

    def edges_touching(self, services: set[str]) -> list[Edge]:
        return [e for e in self.edges if e.source in services and e.target in services]
