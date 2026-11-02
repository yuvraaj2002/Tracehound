"""Service catalog contracts: what Tracehound understood from a user's catalog-info.yaml."""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict

from tracehound.schemas.telemetry import Edge, ServiceNode, Topology

# Backstage kinds that become nodes. Components are the user's own services; resources are what
# they depend on (databases, queues, buckets).
EntityKind = Literal["Component", "Resource"]


class CatalogEntity(BaseModel):
    """One Backstage Component or Resource."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    entity_kind: EntityKind
    # Backstage `spec.type`, e.g. "service", "website" or "database".
    type: str
    # What Tracehound calls it in a topology: "http" for a service, or a resource's engine,
    # e.g. "postgres", from the `tracehound.dev/kind` annotation.
    kind: str
    owner: str
    title: str | None = None
    description: str | None = None
    system: str | None = None
    lifecycle: str | None = None
    # `github.com/project-slug` annotation, owner/name.
    repository: str | None = None


class ServiceCatalog(BaseModel):
    """The entities and `dependsOn` edges parsed from a catalog, ready to store as JSON."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    entities: list[CatalogEntity]
    edges: list[Edge]
    # Entities of other kinds (System, Group, API, ...) that were read but aren't graph nodes.
    ignored: dict[str, int] = {}

    def to_topology(self) -> Topology:
        """The dependency graph triage reads; owners become teams."""
        return Topology(
            services=[ServiceNode(id=e.name, kind=e.kind, team=e.owner) for e in self.entities],
            edges=self.edges,
        )


class CatalogSummary(ServiceCatalog):
    """Response for ``GET``/``PUT /v1/catalog``: the parsed catalog and the file it came from."""

    source: str
    updated_at: AwareDatetime


class CatalogSample(ServiceCatalog):
    """Response for ``GET /v1/catalog/sample``: an example catalog and the file it came from."""

    source: str
