from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tracehound.api.app import create_app
from tracehound.api.dependencies import get_current_user, get_incident_helper, get_token_verifier
from tracehound.auth import InvalidToken, User
from tracehound.schemas import (
    IncidentAccepted,
    IncidentCreateRequest,
    IncidentListQuery,
    IncidentPage,
    IncidentRecord,
    IncidentStats,
    IncidentStatsQuery,
)

VALID = {
    "service_id": "checkout-api",
    "symptom": "p95 latency jumped from 200ms to 3s",
    "window_start": "2026-10-17T14:00:00Z",
    "window_end": "2026-10-17T15:00:00Z",
    "severity": "high",
    "trace_id": "abc123",
}

USER_ID = uuid4()
OTHER_USER_ID = uuid4()

STATS_RANGE = {"from": "2026-10-01T00:00:00Z", "to": "2026-10-03T00:00:00Z"}
# MemoryHelper stamps created_at with now(), so list within a range around it.
_NOW = datetime.now(UTC)
LIST_RANGE = {
    "from": (_NOW - timedelta(days=1)).isoformat(),
    "to": (_NOW + timedelta(days=1)).isoformat(),
}


class MemoryHelper:
    """In-memory stand-in for `IncidentHelper`, so these tests need no database."""

    def __init__(self) -> None:
        self.records: list[tuple[UUID, IncidentRecord]] = []
        self.stats_calls: list[tuple[UUID, IncidentStatsQuery]] = []
        self.list_calls: list[tuple[UUID, IncidentListQuery]] = []

    def create(self, user_id: UUID, request: IncidentCreateRequest) -> IncidentAccepted:
        now = datetime.now(UTC)
        record = IncidentRecord(
            id=uuid4(),
            run_id=uuid4(),
            state="CREATED",
            created_at=now,
            updated_at=now,
            **request.model_dump(),
        )
        self.records.insert(0, (user_id, record))
        return IncidentAccepted(
            incident_id=record.id, run_id=record.run_id, status_url=f"/v1/incidents/{record.id}"
        )

    def get(self, user_id: UUID, incident_id: UUID) -> IncidentRecord | None:
        return next((r for o, r in self.records if o == user_id and r.id == incident_id), None)

    def list(self, user_id: UUID, query: IncidentListQuery) -> IncidentPage:
        self.list_calls.append((user_id, query))
        items = [
            r for o, r in self.records if o == user_id and query.from_ <= r.created_at < query.to
        ]
        return IncidentPage(items=items[: query.limit])

    def stats(self, user_id: UUID, query: IncidentStatsQuery) -> IncidentStats:
        self.stats_calls.append((user_id, query))
        zero = {"low": 0, "medium": 0, "high": 0, "critical": 0}
        return IncidentStats(
            from_=query.from_,
            to=query.to,
            total=3,
            previous_total=1,
            by_severity={**zero, "high": 2, "low": 1},
            by_state={"CREATED": 3},
            top_services=[{"service_id": "checkout-api", "count": 3}],
            timeseries=[
                {"day": date(2026, 10, 1), "total": 3, **zero, "high": 2, "low": 1},
                {"day": date(2026, 10, 2), "total": 0, **zero},
            ],
            avg_window_seconds=1800.0,
            trace_coverage=2 / 3,
        )


class BrokenHelper:
    def create(self, user_id: UUID, request: IncidentCreateRequest) -> IncidentAccepted:
        raise psycopg.OperationalError("connection lost")

    def list(self, user_id: UUID, query: IncidentListQuery) -> IncidentPage:
        raise psycopg.OperationalError("connection lost")

    def stats(self, user_id: UUID, query: IncidentStatsQuery) -> IncidentStats:
        raise psycopg.OperationalError("connection lost")


class RejectingVerifier:
    def verify(self, token: str) -> User:
        raise InvalidToken(token)


def _app_with(helper: object, user_id: UUID | None = USER_ID) -> FastAPI:
    # The lifespan never runs because TestClient is not used as a context manager,
    # so no database pool is opened. `user_id=None` signs nobody in: every token is rejected.
    app = create_app(pool_factory=lambda: pytest.fail("pool should not open"))
    app.dependency_overrides[get_incident_helper] = lambda: helper
    if user_id is None:
        app.dependency_overrides[get_token_verifier] = RejectingVerifier
    else:
        app.dependency_overrides[get_current_user] = lambda: User(user_id=user_id)
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


def test_incident_is_stored_for_signed_in_user(client: TestClient, helper: MemoryHelper) -> None:
    client.post("/v1/incidents", json=VALID)
    assert [owner for owner, _ in helper.records] == [USER_ID]


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer nonsense"}])
def test_requires_signed_in_user(helper: MemoryHelper, headers: dict[str, str]) -> None:
    client = TestClient(_app_with(helper, user_id=None))
    assert client.post("/v1/incidents", json=VALID, headers=headers).status_code == 401
    assert client.get("/v1/incidents", params=LIST_RANGE, headers=headers).status_code == 401
    stats = client.get("/v1/incidents/stats", params=STATS_RANGE, headers=headers)
    assert stats.status_code == 401
    assert helper.records == []
    assert helper.stats_calls == []


def test_user_cannot_see_another_users_incidents(helper: MemoryHelper) -> None:
    mine = TestClient(_app_with(helper))
    created = mine.post("/v1/incidents", json=VALID).json()
    other = TestClient(_app_with(helper, OTHER_USER_ID))
    assert other.get("/v1/incidents", params=LIST_RANGE).json()["items"] == []
    page = mine.get("/v1/incidents", params=LIST_RANGE).json()
    assert [item["id"] for item in page["items"]] == [created["incident_id"]]


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
    response = client.get("/v1/incidents", params=LIST_RANGE)
    assert response.status_code == 200
    assert response.json() == {"items": [], "next_cursor": None}


def test_list_passes_range_and_paging_to_helper(client: TestClient, helper: MemoryHelper) -> None:
    params = {**STATS_RANGE, "cursor": "abc", "limit": "5"}
    assert client.get("/v1/incidents", params=params).status_code == 200
    [(user_id, query)] = helper.list_calls
    assert user_id == USER_ID
    assert (query.from_, query.to) == (
        datetime(2026, 10, 1, tzinfo=UTC),
        datetime(2026, 10, 3, tzinfo=UTC),
    )
    assert (query.cursor, query.limit) == ("abc", 5)


@pytest.mark.parametrize(
    "params",
    [
        {},  # range is required
        {"from": "2026-10-03T00:00:00Z", "to": "2026-10-01T00:00:00Z"},
        {**STATS_RANGE, "limit": "0"},
        {**STATS_RANGE, "limit": "101"},
    ],
)
def test_list_rejects_invalid_query(client: TestClient, params: dict[str, str]) -> None:
    assert client.get("/v1/incidents", params=params).status_code == 422


def test_database_error_returns_500() -> None:
    client = TestClient(_app_with(BrokenHelper()))
    assert client.post("/v1/incidents", json=VALID).status_code == 500
    response = client.get("/v1/incidents", params=LIST_RANGE)
    assert response.status_code == 500
    assert response.json() == {"detail": "Could not load incidents."}
    response = client.get("/v1/incidents/stats", params=STATS_RANGE)
    assert response.status_code == 500
    assert response.json() == {"detail": "Could not load incident stats."}


def test_stats_are_computed_for_signed_in_user(client: TestClient, helper: MemoryHelper) -> None:
    response = client.get(
        "/v1/incidents/stats",
        params={"from": "2026-10-01T05:30:00+05:30", "to": "2026-10-03T00:00:00Z"},
    )
    assert response.status_code == 200
    [(owner, query)] = helper.stats_calls
    assert owner == USER_ID
    assert query.from_ == datetime(2026, 10, 1, tzinfo=UTC)  # normalised to UTC
    assert query.to == datetime(2026, 10, 3, tzinfo=UTC)


def test_stats_response_shape(client: TestClient) -> None:
    body = client.get("/v1/incidents/stats", params=STATS_RANGE).json()
    assert body == {
        "from": "2026-10-01T00:00:00Z",
        "to": "2026-10-03T00:00:00Z",
        "total": 3,
        "previous_total": 1,
        "by_severity": {"low": 1, "medium": 0, "high": 2, "critical": 0},
        "by_state": {"CREATED": 3},
        "top_services": [{"service_id": "checkout-api", "count": 3}],
        "timeseries": [
            {"day": "2026-10-01", "total": 3, "low": 1, "medium": 0, "high": 2, "critical": 0},
            {"day": "2026-10-02", "total": 0, "low": 0, "medium": 0, "high": 0, "critical": 0},
        ],
        "avg_window_seconds": 1800.0,
        "trace_coverage": pytest.approx(2 / 3),
    }


def test_stats_range_may_span_a_full_leap_year(client: TestClient) -> None:
    params = {"from": "2028-01-01T00:00:00Z", "to": "2029-01-01T00:00:00Z"}
    assert client.get("/v1/incidents/stats", params=params).status_code == 200


@pytest.mark.parametrize(
    "params",
    [
        {"to": "2026-10-03T00:00:00Z"},  # from missing
        {"from": "2026-10-01T00:00:00Z"},  # to missing
        {"from": "2026-10-01T00:00:00", "to": "2026-10-03T00:00:00Z"},  # naive from
        {"from": "2026-10-01T00:00:00Z", "to": "2026-10-03T00:00:00"},  # naive to
        {"from": "2026-10-03T00:00:00Z", "to": "2026-10-01T00:00:00Z"},  # reversed
        {"from": "2026-10-01T00:00:00Z", "to": "2026-10-01T00:00:00Z"},  # empty
        {"from": "2026-01-01T00:00:00Z", "to": "2027-01-02T00:00:01Z"},  # over 366 days
        {"from": "yesterday", "to": "2026-10-03T00:00:00Z"},
        {**STATS_RANGE, "unexpected": "param"},
    ],
)
def test_stats_rejects_invalid_range(
    client: TestClient, helper: MemoryHelper, params: dict[str, str]
) -> None:
    assert client.get("/v1/incidents/stats", params=params).status_code == 422
    assert helper.stats_calls == []
