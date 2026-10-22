from datetime import UTC, datetime
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tracehound.api.app import create_app
from tracehound.api.dependencies import get_incident_helper
from tracehound.schemas import IncidentAccepted, IncidentCreateRequest, IncidentRecord

VALID = {
    "service_id": "checkout-api",
    "symptom": "p95 latency jumped from 200ms to 3s",
    "window_start": "2026-10-17T14:00:00Z",
    "window_end": "2026-10-17T15:00:00Z",
    "severity": "high",
    "trace_id": "abc123",
}


class MemoryHelper:
    """In-memory stand-in for `IncidentHelper`, so these tests need no database."""

    def __init__(self) -> None:
        self.records: list[IncidentRecord] = []

    def create(self, request: IncidentCreateRequest) -> IncidentAccepted:
        now = datetime.now(UTC)
        record = IncidentRecord(
            id=uuid4(),
            run_id=uuid4(),
            state="CREATED",
            created_at=now,
            updated_at=now,
            **request.model_dump(),
        )
        self.records.insert(0, record)
        return IncidentAccepted(
            incident_id=record.id, run_id=record.run_id, status_url=f"/v1/incidents/{record.id}"
        )

    def get(self, incident_id: UUID) -> IncidentRecord | None:
        return next((r for r in self.records if r.id == incident_id), None)

    def list_all(self) -> list[IncidentRecord]:
        return list(self.records)


class BrokenHelper:
    def create(self, request: IncidentCreateRequest) -> IncidentAccepted:
        raise psycopg.OperationalError("connection lost")

    def list_all(self) -> list[IncidentRecord]:
        raise psycopg.OperationalError("connection lost")


def _app_with(helper: object) -> FastAPI:
    # The lifespan never runs because TestClient is not used as a context manager,
    # so no database pool is opened.
    app = create_app(pool_factory=lambda: pytest.fail("pool should not open"))
    app.dependency_overrides[get_incident_helper] = lambda: helper
    return app


@pytest.fixture
def helper() -> MemoryHelper:
    return MemoryHelper()


@pytest.fixture
def client(helper: MemoryHelper) -> TestClient:
    return TestClient(_app_with(helper))


def test_accepts_valid_request(client: TestClient) -> None:
    response = client.post("/v1/incidents", json=VALID)
    assert response.status_code == 202
    body = response.json()
    assert body["status_url"] == f"/v1/incidents/{body['incident_id']}"
    assert body["run_id"]


def test_trace_id_is_optional(client: TestClient) -> None:
    payload = {k: v for k, v in VALID.items() if k != "trace_id"}
    assert client.post("/v1/incidents", json=payload).status_code == 202


@pytest.mark.parametrize(
    "override",
    [
        {"window_end": "2026-10-17T13:00:00Z"},  # ends before it starts
        {"window_start": "2026-10-17T14:00:00"},  # naive timestamp
        {"severity": "urgent"},
        {"service_id": "bad id!"},
        {"symptom": ""},
        {"unexpected": "field"},
    ],
)
def test_rejects_invalid_request(client: TestClient, override: dict[str, str]) -> None:
    response = client.post("/v1/incidents", json={**VALID, **override})
    assert response.status_code == 422


def test_rejected_request_is_not_stored(client: TestClient, helper: MemoryHelper) -> None:
    client.post("/v1/incidents", json={**VALID, "severity": "urgent"})
    assert helper.records == []


def test_list_incidents_is_empty_initially(client: TestClient) -> None:
    response = client.get("/v1/incidents")
    assert response.status_code == 200
    assert response.json() == []


def test_database_error_returns_500() -> None:
    client = TestClient(_app_with(BrokenHelper()))
    assert client.post("/v1/incidents", json=VALID).status_code == 500
    response = client.get("/v1/incidents")
    assert response.status_code == 500
    assert response.json() == {"detail": "Could not load incidents."}
