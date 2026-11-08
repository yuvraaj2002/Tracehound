"""Service dependency graph as the dependency tools return it."""

from pydantic import BaseModel, ConfigDict


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
