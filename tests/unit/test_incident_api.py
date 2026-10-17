import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tracehound.api.app import create_app
from tracehound.api.dependencies import get_incident_helper

VALID = {
    "service_id": "checkout-api",
    "symptom": "p95 latency jumped from 200ms to 3s",
    "window_start": "2026-10-17T14:00:00Z",
    "window_end": "2026-10-17T15:00:00Z",
    "severity": "high",
    "trace_id": "abc123",
}


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture
def client(db_path: Path) -> TestClient:
    return TestClient(create_app(db_path))


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


def test_incident_is_persisted(client: TestClient, db_path: Path) -> None:
    body = client.post("/v1/incidents", json=VALID).json()
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM incidents WHERE id = ?", (body["incident_id"],)
        ).fetchone()
    assert row["run_id"] == body["run_id"]
    assert row["service_id"] == "checkout-api"
    assert row["severity"] == "high"
    assert row["trace_id"] == "abc123"
    assert row["window_start"] == "2026-10-17T14:00:00+00:00"
    assert row["state"] == "CREATED"
    assert row["created_at"]


def test_rejected_request_is_not_persisted(client: TestClient, db_path: Path) -> None:
    client.post("/v1/incidents", json={**VALID, "severity": "urgent"})
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM incidents").fetchone()[0] == 0


def test_list_incidents_is_empty_initially(client: TestClient) -> None:
    response = client.get("/v1/incidents")
    assert response.status_code == 200
    assert response.json() == []


def test_list_incidents_returns_all_newest_first(client: TestClient) -> None:
    first = client.post("/v1/incidents", json=VALID).json()
    second = client.post("/v1/incidents", json={**VALID, "service_id": "payments"}).json()
    response = client.get("/v1/incidents")
    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body] == [second["incident_id"], first["incident_id"]]
    assert body[0]["service_id"] == "payments"
    assert body[1]["severity"] == "high"
    assert body[1]["state"] == "CREATED"
    assert body[1]["window_start"] == "2026-10-17T14:00:00Z"


def test_database_error_returns_500(client: TestClient, db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute("DROP TABLE incidents")
    assert client.post("/v1/incidents", json=VALID).status_code == 500
    response = client.get("/v1/incidents")
    assert response.status_code == 500
    assert response.json() == {"detail": "Could not load incidents."}


def test_helper_dependency_can_be_overridden(db_path: Path) -> None:
    class FakeHelper:
        def list_all(self) -> list[object]:
            return []

    app = create_app(db_path)
    client = TestClient(app)
    client.post("/v1/incidents", json=VALID)
    assert len(client.get("/v1/incidents").json()) == 1

    app.dependency_overrides[get_incident_helper] = FakeHelper
    assert client.get("/v1/incidents").json() == []
