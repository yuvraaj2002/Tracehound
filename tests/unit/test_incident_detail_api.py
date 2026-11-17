from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from tracehound.api.app import create_app
from tracehound.api.dependencies import (
    get_current_user,
    get_investigation_store,
    get_token_verifier,
)
from tracehound.auth import InvalidToken, User
from tracehound.schemas import IncidentDetail, IncidentRecord, InvestigationResult

USER_ID = uuid4()
OTHER_USER_ID = uuid4()
NOW = datetime(2026, 10, 29, 14, 10, tzinfo=UTC)


def _record(state: str = "CREATED") -> IncidentRecord:
    return IncidentRecord(
        id=uuid4(),
        run_id=uuid4(),
        state=state,
        created_at=NOW,
        updated_at=NOW,
        service_id="checkout-api",
        symptom="p95 latency jumped from 200ms to 3s",
        window_start=datetime(2026, 10, 29, 14, tzinfo=UTC),
        window_end=datetime(2026, 10, 29, 14, 30, tzinfo=UTC),
        severity="high",
        trace_id=None,
    )


def _result(record: IncidentRecord) -> InvestigationResult:
    evidence_id = "log-001"
    return InvestigationResult.model_validate(
        {
            "incident_id": record.id,
            "run_id": record.run_id,
            "findings": [
                {
                    "specialist": "logs",
                    "claim": "Timeouts to payments",
                    "evidence_ids": [evidence_id],
                }
            ],
            "evidence": [
                {
                    "id": evidence_id,
                    "run_id": record.run_id,
                    "source_type": "log",
                    "source_locator": "loki://checkout-api?ts=1",
                    "service": "checkout-api",
                    "event_time": NOW,
                    "collected_at": NOW,
                    "payload_hash": "0" * 64,
                    "excerpt": "upstream timeout after 3000ms",
                }
            ],
            "hypotheses": [
                {
                    "run_id": record.run_id,
                    "statement": "Payments is slow",
                    "mechanism": "Checkout waits on payments",
                    "confidence": "medium",
                    "confidence_rationale": "One log source",
                    "supporting_evidence_ids": [evidence_id],
                    "verification_steps": [
                        {"check": "Payments p95", "expected_if_true": "Above 2s"}
                    ],
                }
            ],
            "agent_runs": {"triage": {"status": "completed"}, "logs": {"status": "completed"}},
            "started_at": NOW,
            "finished_at": NOW,
        }
    )


class MemoryStore:
    """In-memory stand-in for `InvestigationStore`."""

    def __init__(self) -> None:
        self.details: list[tuple[UUID, IncidentDetail]] = []

    def add(self, user_id: UUID, detail: IncidentDetail) -> IncidentDetail:
        self.details.append((user_id, detail))
        return detail

    def get(self, user_id: UUID, incident_id: UUID) -> IncidentDetail | None:
        return next(
            (d for o, d in self.details if o == user_id and d.incident.id == incident_id), None
        )


class BrokenStore:
    def get(self, user_id: UUID, incident_id: UUID) -> IncidentDetail | None:
        raise OperationalError("SELECT 1", None, Exception("connection lost"))


class RejectingVerifier:
    def verify(self, token: str) -> User:
        raise InvalidToken(token)


def _app_with(store: object, user_id: UUID | None = USER_ID) -> FastAPI:
    app = create_app(engine_factory=lambda: pytest.fail("engine should not be created"))
    app.dependency_overrides[get_investigation_store] = lambda: store
    if user_id is None:
        app.dependency_overrides[get_token_verifier] = RejectingVerifier
    else:
        app.dependency_overrides[get_current_user] = lambda: User(user_id=user_id)
    return app


@pytest.fixture
def store() -> MemoryStore:
    return MemoryStore()


def test_returns_incident_without_result(store: MemoryStore) -> None:
    record = _record()
    store.add(USER_ID, IncidentDetail(incident=record))
    response = TestClient(_app_with(store)).get(f"/v1/incidents/{record.id}")
    assert response.status_code == 200
    body = response.json()
    assert body["incident"]["id"] == str(record.id)
    assert body["incident"]["state"] == "CREATED"
    assert body["result"] is None


def test_returns_incident_with_result(store: MemoryStore) -> None:
    record = _record("COMPLETED")
    store.add(USER_ID, IncidentDetail(incident=record, result=_result(record)))
    response = TestClient(_app_with(store)).get(f"/v1/incidents/{record.id}")
    assert response.status_code == 200
    result = response.json()["result"]
    assert result["run_id"] == str(record.run_id)
    assert [f["evidence_ids"] for f in result["findings"]] == [["log-001"]]
    assert result["evidence"][0]["id"] == "log-001"
    assert result["hypotheses"][0]["verification_steps"][0]["check"] == "Payments p95"
    assert result["agent_runs"]["logs"]["status"] == "completed"


def test_missing_incident_returns_404(store: MemoryStore) -> None:
    response = TestClient(_app_with(store)).get(f"/v1/incidents/{uuid4()}")
    assert response.status_code == 404
    assert response.json() == {"detail": "Incident not found."}


def test_user_cannot_see_another_users_incident(store: MemoryStore) -> None:
    record = _record()
    store.add(USER_ID, IncidentDetail(incident=record))
    response = TestClient(_app_with(store, OTHER_USER_ID)).get(f"/v1/incidents/{record.id}")
    assert response.status_code == 404


def test_rejects_non_uuid_id(store: MemoryStore) -> None:
    assert TestClient(_app_with(store)).get("/v1/incidents/not-a-uuid").status_code == 422


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer nonsense"}])
def test_requires_signed_in_user(store: MemoryStore, headers: dict[str, str]) -> None:
    client = TestClient(_app_with(store, user_id=None))
    assert client.get(f"/v1/incidents/{uuid4()}", headers=headers).status_code == 401


def test_database_error_returns_500() -> None:
    response = TestClient(_app_with(BrokenStore())).get(f"/v1/incidents/{uuid4()}")
    assert response.status_code == 500
    assert response.json() == {"detail": "Could not load the incident."}
