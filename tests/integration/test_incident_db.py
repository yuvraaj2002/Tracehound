"""Incident API against real PostgreSQL. Run with: uv run pytest -m integration

Each test gets a throwaway schema built from `supabase/migrations`, so real data is
never read or written.
"""

import os
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg_pool import ConnectionPool

from tracehound.api.app import create_app
from tracehound.db import create_pool

MIGRATIONS = Path(__file__).resolve().parents[2] / "supabase" / "migrations"

VALID = {
    "service_id": "checkout-api",
    "symptom": "p95 latency jumped from 200ms to 3s",
    "window_start": "2026-10-17T14:00:00Z",
    "window_end": "2026-10-17T15:00:00Z",
    "severity": "high",
    "trace_id": "abc123",
}

load_dotenv()
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="DATABASE_URL is not set"),
]


@pytest.fixture
def schema() -> Iterator[str]:
    """Create a schema holding every migration, and drop it afterwards."""
    name = f"test_{uuid4().hex[:12]}"
    with psycopg.connect(os.environ["DATABASE_URL"], prepare_threshold=None) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(name)))
        conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(name)))
        for migration in sorted(MIGRATIONS.glob("*.sql")):
            conn.execute(migration.read_text())
    try:
        yield name
    finally:
        with psycopg.connect(os.environ["DATABASE_URL"], prepare_threshold=None) as conn:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(name)))


@pytest.fixture
def pool(schema: str) -> Iterator[ConnectionPool]:
    """A pool whose connections only see the test schema."""
    with create_pool(os.environ["DATABASE_URL"], options=f"-c search_path={schema}") as test_pool:
        yield test_pool


@pytest.fixture
def client(pool: ConnectionPool) -> Iterator[TestClient]:
    # The app's lifespan closes the pool it is given; the fixture's `with` tolerates that.
    with TestClient(create_app(pool_factory=lambda: pool)) as test_client:
        yield test_client


def test_incident_is_persisted(client: TestClient, pool: ConnectionPool) -> None:
    body = client.post("/v1/incidents", json=VALID).json()
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT * FROM incidents WHERE id = %s", (body["incident_id"],)
        ).fetchone()
    assert row is not None
    assert str(row["run_id"]) == body["run_id"]
    assert row["service_id"] == "checkout-api"
    assert row["severity"] == "high"
    assert row["trace_id"] == "abc123"
    assert row["window_start"].isoformat() == "2026-10-17T14:00:00+00:00"
    assert row["state"] == "CREATED"
    assert row["created_at"]


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


def test_database_error_returns_500(client: TestClient, pool: ConnectionPool) -> None:
    with pool.connection() as conn:
        conn.execute("DROP TABLE incidents")
    assert client.post("/v1/incidents", json=VALID).status_code == 500
    assert client.get("/v1/incidents").status_code == 500
