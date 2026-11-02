from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from tests.unit.test_api_keys import USER_ID, VERIFIER, _auth
from tracehound.api.app import create_app
from tracehound.api.dependencies import get_catalog_store, get_token_verifier
from tracehound.helpers.catalog_helper import CatalogInvalid, parse_catalog
from tracehound.schemas.catalog import CatalogSummary, ServiceCatalog

CATALOG = """\
apiVersion: backstage.io/v1alpha1
kind: System
metadata: {name: checkout}
spec: {owner: team-checkout}
---
apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: checkout-api
  annotations: {github.com/project-slug: acme/checkout}
spec:
  type: service
  owner: group:default/team-checkout
  system: checkout
  dependsOn: [resource:orders-db, component:orders]
---
apiVersion: backstage.io/v1alpha1
kind: Component
metadata: {name: orders}
spec: {type: service, owner: team-checkout}
---
apiVersion: backstage.io/v1alpha1
kind: Resource
metadata:
  name: orders-db
  annotations: {tracehound.dev/kind: postgres}
spec: {type: database, owner: team-platform, dependencyOf: [component:orders]}
"""


def _problems(source: str) -> list[str]:
    with pytest.raises(CatalogInvalid) as caught:
        parse_catalog(source)
    return caught.value.problems


# Parsing


def test_parses_components_resources_and_both_edge_directions() -> None:
    catalog = parse_catalog(CATALOG)
    topology = catalog.to_topology()
    assert {(s.id, s.kind, s.team) for s in topology.services} == {
        ("checkout-api", "http", "team-checkout"),
        ("orders", "http", "team-checkout"),
        ("orders-db", "postgres", "team-platform"),
    }
    assert {(e.source, e.target, e.protocol) for e in topology.edges} == {
        ("checkout-api", "orders", "http"),
        ("checkout-api", "orders-db", "postgres"),
        ("orders", "orders-db", "postgres"),  # from orders-db's dependencyOf
    }
    checkout = next(e for e in catalog.entities if e.name == "checkout-api")
    assert (checkout.repository, checkout.system) == ("acme/checkout", "checkout")
    assert catalog.ignored == {"System": 1}


def test_resource_kind_falls_back_to_spec_type() -> None:
    source = CATALOG.replace("  annotations: {tracehound.dev/kind: postgres}\n", "")
    assert parse_catalog(source).to_topology().services[-1].kind == "database"


def test_reports_every_problem_at_once() -> None:
    source = CATALOG.replace("resource:orders-db, component:orders", "resource:orders-dbb")
    source = source.replace("{type: service, owner: team-checkout}", "{type: service}")
    assert _problems(source) == [
        "Component orders: spec.owner is required",
        "checkout-api: spec.dependsOn names resource:orders-dbb, which isn't in this catalog",
        # orders is in the file, just invalid, so orders-db's link to it isn't reported too.
    ]


def test_ref_kind_must_match_the_entity() -> None:
    source = CATALOG.replace("resource:orders-db, component:orders", "component:orders-db")
    assert _problems(source) == [
        "checkout-api: spec.dependsOn names component:orders-db, which isn't in this catalog"
    ]


@pytest.mark.parametrize(
    ("source", "problem"),
    [
        ("kind: [unclosed", "not valid YAML at line 1"),
        ("apiVersion: v1\nkind: Pod\nmetadata: {name: x}", "entity 1: apiVersion must be"),
        ("- just\n- a list", "entity 1: expected a mapping"),
        ("apiVersion: backstage.io/v1alpha1\nkind: Group\nmetadata: {name: g}", "no Component"),
    ],
)
def test_rejects_unusable_input(source: str, problem: str) -> None:
    assert _problems(source)[0].startswith(problem)


def test_duplicate_names_are_rejected() -> None:
    duplicate = "---\napiVersion: backstage.io/v1alpha1\nkind: Component\n"
    duplicate += "metadata: {name: orders}\nspec: {type: service, owner: x}\n"
    assert "the name orders is used more than once" in _problems(CATALOG + duplicate)[0]


def test_yaml_tags_cannot_build_python_objects() -> None:
    assert _problems("!!python/object/apply:os.system ['true']")[0].startswith("not valid YAML")


# API


class MemoryCatalogs:
    def __init__(self) -> None:
        self.rows: dict[UUID, CatalogSummary] = {}

    def get(self, user_id: UUID) -> CatalogSummary | None:
        return self.rows.get(user_id)

    def put(self, user_id: UUID, source: str, catalog: ServiceCatalog) -> CatalogSummary:
        summary = CatalogSummary(
            source=source, updated_at=datetime.now(UTC), **catalog.model_dump()
        )
        self.rows[user_id] = summary
        return summary


@pytest.fixture
def catalogs() -> MemoryCatalogs:
    return MemoryCatalogs()


@pytest.fixture
def client(catalogs: MemoryCatalogs) -> TestClient:
    app = create_app(engine_factory=lambda: pytest.fail("engine should not be created"))
    app.dependency_overrides[get_catalog_store] = lambda: catalogs
    app.dependency_overrides[get_token_verifier] = lambda: VERIFIER
    return TestClient(app)


def _put(client: TestClient, body: str | bytes):
    headers = {**_auth(), "Content-Type": "application/yaml"}
    return client.put("/v1/catalog", content=body, headers=headers)


def test_get_is_404_before_an_upload(client: TestClient) -> None:
    assert client.get("/v1/catalog", headers=_auth()).status_code == 404


def test_put_then_get_round_trips_the_file(client: TestClient, catalogs: MemoryCatalogs) -> None:
    response = _put(client, CATALOG)
    assert response.status_code == 200
    assert len(response.json()["entities"]) == 3
    stored = client.get("/v1/catalog", headers=_auth()).json()
    assert stored["source"] == CATALOG
    assert catalogs.get(USER_ID) is not None


def test_put_replaces_the_previous_catalog(client: TestClient) -> None:
    _put(client, CATALOG)
    smaller = CATALOG.split("---\n")[2]  # just `orders`
    assert [e["name"] for e in _put(client, smaller).json()["entities"]] == ["orders"]


def test_invalid_catalog_is_422_with_every_problem(
    client: TestClient, catalogs: MemoryCatalogs
) -> None:
    response = _put(
        client, CATALOG.replace("orders-db, component:orders]", "orders-db, component:nope]")
    )
    assert response.status_code == 422
    assert response.json()["detail"] == [
        "checkout-api: spec.dependsOn names component:nope, which isn't in this catalog"
    ]
    assert catalogs.rows == {}


def test_non_utf8_and_oversized_bodies_are_rejected(client: TestClient) -> None:
    assert _put(client, b"\xff\xfe").status_code == 422
    assert _put(client, b"a" * 1_048_577).status_code == 413


def test_catalog_needs_a_session(client: TestClient) -> None:
    assert client.get("/v1/catalog").status_code == 401
    assert client.put("/v1/catalog", content=CATALOG).status_code == 401


def test_an_invalid_entity_still_has_its_dependencies_checked() -> None:
    source = (
        "apiVersion: backstage.io/v1alpha1\nkind: Component\nmetadata: {name: checkout-api}\n"
        "spec: {type: service, dependsOn: [resource:orders-dbb]}\n"
    )
    assert _problems(source) == [
        "Component checkout-api: spec.owner is required",
        "checkout-api: spec.dependsOn names resource:orders-dbb, which isn't in this catalog",
    ]


# Sample


def test_sample_catalog_is_valid_and_has_a_graph() -> None:
    from tracehound.helpers.catalog_helper import sample_catalog

    sample = sample_catalog()
    assert sample.edges
    assert {e.entity_kind for e in sample.entities} == {"Component", "Resource"}
    assert sample.ignored == {"Group": 2, "System": 1}
    assert "kind: Component" in sample.source


def test_sample_endpoint_returns_it_without_saving(
    client: TestClient, catalogs: MemoryCatalogs
) -> None:
    response = client.get("/v1/catalog/sample", headers=_auth())
    assert response.status_code == 200
    body = response.json()
    assert body["entities"] and body["edges"] and body["source"]
    assert client.get("/v1/catalog", headers=_auth()).status_code == 404


def test_sample_endpoint_needs_a_session(client: TestClient) -> None:
    assert client.get("/v1/catalog/sample").status_code == 401


# Validate


def test_validate_returns_the_graph_and_saves_nothing(client: TestClient) -> None:
    response = client.post(
        "/v1/catalog/validate",
        content=CATALOG,
        headers={**_auth(), "Content-Type": "application/yaml"},
    )
    assert response.status_code == 200
    assert {e["name"] for e in response.json()["entities"]} == {
        "checkout-api",
        "orders",
        "orders-db",
    }
    assert client.get("/v1/catalog", headers=_auth()).status_code == 404


def test_validate_reports_every_problem_and_needs_a_session(client: TestClient) -> None:
    bad = CATALOG.replace("orders-db, component:orders]", "orders-db, component:nope]")
    response = client.post(
        "/v1/catalog/validate", content=bad, headers={**_auth(), "Content-Type": "application/yaml"}
    )
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)
    assert client.post("/v1/catalog/validate", content=CATALOG).status_code == 401
