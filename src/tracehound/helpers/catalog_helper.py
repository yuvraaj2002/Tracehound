"""Parse a Backstage catalog-info.yaml into a `ServiceCatalog`, and store one per user."""

import re
from collections import Counter
from functools import cache
from importlib.resources import files
from typing import Any
from uuid import UUID

import yaml
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert

from tracehound.db import SessionFactory
from tracehound.models import ServiceCatalogRow
from tracehound.schemas.catalog import (
    CatalogEntity,
    CatalogSample,
    CatalogSummary,
    ServiceCatalog,
)
from tracehound.schemas.telemetry import Edge

MAX_CATALOG_BYTES = 1_048_576  # matches the column check
MAX_ENTITIES = 500
NODE_KINDS = {"component": "Component", "resource": "Resource"}
# Backstage's own rule for metadata.name.
_NAME = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9_.-]{0,61}[A-Za-z0-9])?$")
_SLUG = re.compile(r"^[\w.-]+/[\w.-]+$")
KIND_ANNOTATION = "tracehound.dev/kind"
REPO_ANNOTATION = "github.com/project-slug"


class CatalogInvalid(Exception):
    """The catalog can't be used. `problems` lists every reason, each safe to show the user."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


def _ref(ref: Any) -> tuple[str | None, str]:
    """Split a Backstage entity ref, ``[kind:][namespace/]name``, into (kind, name)."""
    kind, _, rest = str(ref).rpartition(":")
    return (kind.lower() or None), rest.rpartition("/")[2]


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _documents(source: str) -> list[Any]:
    try:
        return [doc for doc in yaml.safe_load_all(source) if doc is not None]
    except yaml.MarkedYAMLError as exc:
        mark = exc.problem_mark
        where = f" at line {mark.line + 1}, column {mark.column + 1}" if mark else ""
        raise CatalogInvalid([f"not valid YAML{where}: {exc.problem}"]) from exc
    except yaml.YAMLError as exc:
        raise CatalogInvalid(["not valid YAML"]) from exc


def parse_catalog(source: str) -> ServiceCatalog:
    """Read Backstage entities (one per ``---`` document) into nodes and ``dependsOn`` edges.

    Components and Resources become nodes; other kinds are counted in ``ignored``. A Component
    is an ``http`` node and a Resource takes its kind from the ``tracehound.dev/kind`` annotation,
    falling back to its ``spec.type``. Edges come from ``spec.dependsOn`` and
    ``spec.dependencyOf``, and must point at an entity in the same catalog. Raises
    ``CatalogInvalid`` listing every problem found.
    """
    if len(source.encode()) > MAX_CATALOG_BYTES:
        raise CatalogInvalid([f"the catalog is larger than {MAX_CATALOG_BYTES // 1024} KB"])
    documents = _documents(source)
    if len(documents) > MAX_ENTITIES:
        raise CatalogInvalid([f"the catalog has more than {MAX_ENTITIES} entities"])

    problems: list[str] = []
    ignored: Counter[str] = Counter()
    entities: dict[str, CatalogEntity] = {}
    declared: dict[str, str] = {}  # every Component/Resource name, valid or not
    links: list[tuple[str, str, str]] = []  # (source, target ref, field) for later resolution

    for index, doc in enumerate(documents, start=1):
        where = f"entity {index}"
        if not isinstance(doc, dict):
            problems.append(f"{where}: expected a mapping with apiVersion, kind and metadata")
            continue
        if not str(doc.get("apiVersion", "")).startswith("backstage.io/"):
            problems.append(f"{where}: apiVersion must be backstage.io/v1alpha1 or similar")
            continue
        kind = NODE_KINDS.get(str(doc.get("kind", "")).lower())
        metadata = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
        spec = doc.get("spec") if isinstance(doc.get("spec"), dict) else {}
        name = _text(metadata.get("name"))
        if not name or not _NAME.match(name):
            problems.append(f"{where}: metadata.name must be 1-63 letters, digits, - _ or .")
            continue
        where = f"{doc.get('kind')} {name}"
        if kind is None:
            ignored[str(doc.get("kind") or "unknown")] += 1
            continue
        if name in declared:
            problems.append(f"{where}: the name {name} is used more than once")
            continue
        # Declared even if invalid below, so its dependencies are still checked and others
        # that point at it aren't reported as dangling on top of its own problem.
        declared[name] = kind
        for field in ("dependsOn", "dependencyOf"):
            refs = spec.get(field) or []
            if not isinstance(refs, list):
                problems.append(f"{where}: spec.{field} must be a list")
                continue
            links.extend((name, str(ref), field) for ref in refs)
        owner = _text(spec.get("owner"))
        spec_type = _text(spec.get("type"))
        if not owner:
            problems.append(f"{where}: spec.owner is required")
        if not spec_type:
            problems.append(f"{where}: spec.type is required")
        if not owner or not spec_type:
            continue
        annotations = metadata.get("annotations")
        annotations = annotations if isinstance(annotations, dict) else {}
        repository = _text(annotations.get(REPO_ANNOTATION))
        if repository and not _SLUG.match(repository):
            problems.append(f"{where}: {REPO_ANNOTATION} must be owner/name")
            repository = None
        node_kind = "http" if kind == "Component" else spec_type
        entities[name] = CatalogEntity(
            name=name,
            entity_kind=kind,  # type: ignore[arg-type]
            type=spec_type,
            kind=_text(annotations.get(KIND_ANNOTATION)) or node_kind,
            owner=_ref(owner)[1],
            title=_text(metadata.get("title")),
            description=_text(metadata.get("description")),
            system=_ref(spec["system"])[1] if _text(spec.get("system")) else None,
            lifecycle=_text(spec.get("lifecycle")),
            repository=repository,
        )

    edges: dict[tuple[str, str], Edge] = {}
    for name, ref, field in links:
        ref_kind, target = _ref(ref)
        target_kind = declared.get(target)
        if target_kind is None or (
            ref_kind is not None and NODE_KINDS.get(ref_kind) != target_kind
        ):
            problems.append(f"{name}: spec.{field} names {ref}, which isn't in this catalog")
            continue
        if name not in entities or target not in entities:
            continue  # one end is invalid and already reported; the catalog will be rejected
        caller, callee = (name, target) if field == "dependsOn" else (target, name)
        protocol = "http" if entities[callee].entity_kind == "Component" else entities[callee].kind
        edges[(caller, callee)] = Edge(source=caller, target=callee, protocol=protocol)

    if not entities and not problems:
        problems.append("no Component or Resource entities found")
    if problems:
        raise CatalogInvalid(problems)
    return ServiceCatalog(
        entities=sorted(entities.values(), key=lambda e: (e.entity_kind, e.name)),
        edges=sorted(edges.values(), key=lambda e: (e.source, e.target)),
        ignored=dict(sorted(ignored.items())),
    )


@cache
def sample_catalog() -> CatalogSample:
    """The bundled example ``catalog-info.yaml``, parsed the same way an upload is."""
    source = files("tracehound.resources").joinpath("catalog-info.yaml").read_text("utf-8")
    return CatalogSample(source=source, **parse_catalog(source).model_dump())


class CatalogStore:
    """Each user's uploaded catalog, one row per user."""

    def __init__(self, sessions: SessionFactory) -> None:
        self._sessions = sessions

    def get(self, user_id: UUID) -> CatalogSummary | None:
        with self._sessions() as session:
            row = session.get(ServiceCatalogRow, user_id)
        if row is None:
            return None
        return CatalogSummary(source=row.source, updated_at=row.updated_at, **row.catalog)

    def put(self, user_id: UUID, source: str, catalog: ServiceCatalog) -> CatalogSummary:
        """Replace the user's catalog with `source`, already parsed into `catalog`."""
        stmt = insert(ServiceCatalogRow).values(
            user_id=user_id, source=source, catalog=catalog.model_dump(mode="json")
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[ServiceCatalogRow.user_id],
            set_={
                "source": stmt.excluded.source,
                "catalog": stmt.excluded.catalog,
                "updated_at": func.now(),
            },
        ).returning(ServiceCatalogRow.updated_at)
        with self._sessions.begin() as session:
            updated_at = session.execute(stmt).scalar_one()
        return CatalogSummary(source=source, updated_at=updated_at, **catalog.model_dump())
