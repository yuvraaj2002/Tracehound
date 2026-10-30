"""Incident API against real PostgreSQL. Run with: uv run pytest -m integration

Each test gets a throwaway schema built from `supabase/migrations`, so real data is
never read or written. `incidents.user_id` references `auth.users`, so the tests borrow an
existing Supabase user and are skipped if there is none.
"""

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg_pool import ConnectionPool

from tracehound.api.app import create_app
from tracehound.api.dependencies import get_current_user
from tracehound.auth import User
from tracehound.db import create_pool
from tracehound.helpers.incident_helper import IncidentHelper
from tracehound.schemas import IncidentCreateRequest, IncidentListQuery, IncidentStatsQuery

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
def user_id() -> UUID:
    with psycopg.connect(os.environ["DATABASE_URL"], prepare_threshold=None) as conn:
        row = conn.execute("SELECT id FROM auth.users LIMIT 1").fetchone()
    if row is None:
        pytest.skip("no Supabase user to own the test incidents")
    return row[0]


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
def client(pool: ConnectionPool, user_id: UUID) -> Iterator[TestClient]:
    # The app's lifespan closes the pool it is given; the fixture's `with` tolerates that.
    app = create_app(pool_factory=lambda: pool)
    app.dependency_overrides[get_current_user] = lambda: User(user_id=user_id)
    with TestClient(app) as test_client:
        yield test_client


def test_incident_is_persisted(client: TestClient, pool: ConnectionPool, user_id: UUID) -> None:
    body = client.post("/v1/incidents", json=VALID).json()
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT * FROM incidents WHERE id = %s", (body["incident_id"],)
        ).fetchone()
    assert row is not None
    assert str(row["run_id"]) == body["run_id"]
    assert row["user_id"] == user_id
    assert row["service_id"] == "checkout-api"
    assert row["severity"] == "high"
    assert row["trace_id"] == "abc123"
    assert row["window_start"].isoformat() == "2026-10-17T14:00:00+00:00"
    assert row["state"] == "CREATED"
    assert row["created_at"]


def test_list_incidents_returns_range_newest_first(client: TestClient) -> None:
    first = client.post("/v1/incidents", json=VALID).json()
    second = client.post("/v1/incidents", json={**VALID, "service_id": "payments"}).json()
    now = datetime.now(UTC)
    window = {
        "from": (now - timedelta(hours=1)).isoformat(),
        "to": (now + timedelta(hours=1)).isoformat(),
    }
    response = client.get("/v1/incidents", params=window)
    assert response.status_code == 200
    body = response.json()["items"]
    assert [item["id"] for item in body] == [second["incident_id"], first["incident_id"]]
    assert body[0]["service_id"] == "payments"
    assert body[1]["severity"] == "high"
    assert body[1]["state"] == "CREATED"
    assert body[1]["window_start"] == "2026-10-17T14:00:00Z"


def test_user_cannot_see_another_users_incidents(pool: ConnectionPool, user_id: UUID) -> None:
    helper = IncidentHelper(pool)
    created = helper.create(user_id, IncidentCreateRequest.model_validate(VALID))
    stranger = uuid4()  # reads need no auth.users row
    now = datetime.now(UTC)
    window = IncidentListQuery.model_validate(
        {"from": now - timedelta(hours=1), "to": now + timedelta(hours=1)}
    )
    assert helper.list(stranger, window).items == []
    assert helper.get(stranger, created.incident_id) is None
    assert [r.id for r in helper.list(user_id, window).items] == [created.incident_id]
    record = helper.get(user_id, created.incident_id)
    assert record is not None
    assert "user_id" not in record.model_dump()


def _insert(
    pool: ConnectionPool,
    owner: UUID,
    created_at: str,
    service_id: str = "checkout-api",
    severity: str = "low",
    window_seconds: int = 600,
    trace_id: str | None = None,
) -> None:
    """Insert an incident with a chosen `created_at`, which the API always sets to now()."""
    created = datetime.fromisoformat(created_at)
    start = datetime(2026, 9, 1, tzinfo=UTC)
    with pool.connection() as conn:
        conn.execute(
            "INSERT INTO incidents (id, run_id, user_id, service_id, symptom, severity,"
            " window_start, window_end, trace_id, created_at, updated_at)"
            " VALUES (%s, %s, %s, %s, 'symptom', %s, %s, %s, %s, %s, %s)",
            (
                uuid4(),
                uuid4(),
                owner,
                service_id,
                severity,
                start,
                start + timedelta(seconds=window_seconds),
                trace_id,
                created,
                created,
            ),
        )


def test_stats_cover_only_the_users_incidents_in_range(
    client: TestClient, pool: ConnectionPool, user_id: UUID
) -> None:
    # Only one Supabase user can be borrowed, so drop the auth.users reference in this
    # throwaway schema to let a second, made-up user own incidents.
    with pool.connection() as conn:
        conn.execute("ALTER TABLE incidents DROP CONSTRAINT incidents_user_id_fkey")
    stranger = uuid4()

    # In range [2026-10-01, 2026-10-04). None of this user's land on 10-02.
    _insert(
        pool, user_id, "2026-10-01T00:00:00Z", severity="high", window_seconds=3600, trace_id="t1"
    )
    _insert(pool, user_id, "2026-10-01T06:00:00Z", "payments", "medium")
    _insert(pool, user_id, "2026-10-01T23:59:59Z")
    _insert(
        pool,
        user_id,
        "2026-10-03T12:00:00Z",
        severity="critical",
        window_seconds=1200,
        trace_id="t2",
    )
    _insert(pool, user_id, "2026-10-03T23:59:59.999999Z", "payments", "high", trace_id="t3")
    for service in ("zeta", "search", "billing", "auth", "alpha"):
        _insert(pool, user_id, "2026-10-03T05:30:00+05:30", service)  # 10-03 00:00 UTC
    # Previous period [2026-09-28, 2026-10-01).
    _insert(pool, user_id, "2026-09-28T00:00:00Z")
    _insert(pool, user_id, "2026-09-30T23:59:59Z", "payments", "critical")
    # Outside both periods.
    _insert(pool, user_id, "2026-09-27T23:59:59Z", "elsewhere", "critical")
    _insert(pool, user_id, "2026-10-04T00:00:00Z", "elsewhere", "critical")
    # Another user's incidents, in both periods.
    for created_at in ("2026-10-01T12:00:00Z", "2026-10-02T12:00:00Z", "2026-09-29T12:00:00Z"):
        _insert(pool, stranger, created_at, "stranger-svc", "critical", trace_id="t")

    response = client.get(
        "/v1/incidents/stats", params={"from": "2026-10-01T00:00:00Z", "to": "2026-10-04T00:00:00Z"}
    )
    assert response.status_code == 200
    assert response.json() == {
        "from": "2026-10-01T00:00:00Z",
        "to": "2026-10-04T00:00:00Z",
        "total": 10,
        "previous_total": 2,
        "by_severity": {"low": 6, "medium": 1, "high": 2, "critical": 1},
        "by_state": {"CREATED": 10},
        "top_services": [
            {"service_id": "checkout-api", "count": 3},
            {"service_id": "payments", "count": 2},
            {"service_id": "alpha", "count": 1},
            {"service_id": "auth", "count": 1},
            {"service_id": "billing", "count": 1},
        ],
        "timeseries": [
            {"day": "2026-10-01", "total": 3, "low": 1, "medium": 1, "high": 1, "critical": 0},
            {"day": "2026-10-02", "total": 0, "low": 0, "medium": 0, "high": 0, "critical": 0},
            {"day": "2026-10-03", "total": 7, "low": 5, "medium": 0, "high": 1, "critical": 1},
        ],
        # (3600 + 1200 + 8 * 600) / 10
        "avg_window_seconds": 960.0,
        "trace_coverage": 0.3,
    }


def test_stats_are_empty_and_zero_filled_without_incidents(
    pool: ConnectionPool, user_id: UUID
) -> None:
    # A range that starts and ends mid-day still gets a point for each UTC day it touches.
    query = IncidentStatsQuery.model_validate(
        {"from": "2026-10-01T12:00:00Z", "to": "2026-10-03T06:00:00Z"}
    )
    stats = IncidentHelper(pool).stats(user_id, query)
    assert stats.total == 0
    assert stats.previous_total == 0
    assert stats.by_severity.model_dump() == {"low": 0, "medium": 0, "high": 0, "critical": 0}
    assert stats.by_state == {}
    assert stats.top_services == []
    assert [(p.day.isoformat(), p.total) for p in stats.timeseries] == [
        ("2026-10-01", 0),
        ("2026-10-02", 0),
        ("2026-10-03", 0),
    ]
    assert stats.avg_window_seconds is None
    assert stats.trace_coverage is None


def test_database_error_returns_500(client: TestClient, pool: ConnectionPool) -> None:
    with pool.connection() as conn:
        conn.execute("DROP TABLE incidents")
    assert client.post("/v1/incidents", json=VALID).status_code == 500
    stats_range = {"from": "2026-10-01T00:00:00Z", "to": "2026-10-04T00:00:00Z"}
    assert client.get("/v1/incidents", params=stats_range).status_code == 500
    assert client.get("/v1/incidents/stats", params=stats_range).status_code == 500


def test_list_pages_through_the_range_newest_first(pool: ConnectionPool, user_id: UUID) -> None:
    with pool.connection() as conn:  # let a made-up user own one incident, as above
        conn.execute("ALTER TABLE incidents DROP CONSTRAINT incidents_user_id_fkey")
    helper = IncidentHelper(pool)
    for hour in range(5):
        _insert(pool, user_id, f"2026-10-01T0{hour}:00:00+00:00", service_id=f"svc-{hour}")
    _insert(pool, user_id, "2026-10-02T00:00:00+00:00", service_id="at-to")  # excluded: == to
    _insert(pool, user_id, "2026-09-30T23:59:59+00:00", service_id="before")  # excluded
    _insert(pool, uuid4(), "2026-10-01T02:30:00+00:00", service_id="stranger")  # other user
    query = {"from": "2026-10-01T00:00:00Z", "to": "2026-10-02T00:00:00Z", "limit": 2}

    seen: list[str] = []
    cursor = None
    pages = 0
    while True:
        page = helper.list(user_id, IncidentListQuery.model_validate({**query, "cursor": cursor}))
        seen += [r.service_id for r in page.items]
        pages += 1
        cursor = page.next_cursor
        if cursor is None:
            break
    assert seen == ["svc-4", "svc-3", "svc-2", "svc-1", "svc-0"]
    assert pages == 3
