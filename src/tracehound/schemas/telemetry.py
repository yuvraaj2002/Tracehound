"""Telemetry records as the read-only tools return them."""

from datetime import UTC, datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator


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
