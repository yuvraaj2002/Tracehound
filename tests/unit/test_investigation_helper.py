from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy.dialects import postgresql

from tracehound.helpers.investigation_helper import INTERRUPTED_ERROR, InvestigationStore
from tracehound.models import Incident, InvestigationResultRow
from tracehound.schemas import AgentRun, IncidentState


class FakeResult:
    def __init__(self, rows: list[Any]) -> None:
        self.rows = rows

    def first(self) -> Any:
        return self.rows[0] if self.rows else None

    def all(self) -> list[Any]:
        return self.rows


class FakeSession:
    """Records every statement as compiled PostgreSQL and its bound values."""

    def __init__(self, rows: list[Any] | None = None) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.rows = rows or []

    def execute(self, stmt: Any) -> FakeResult:
        compiled = stmt.compile(dialect=postgresql.dialect())
        self.calls.append((str(compiled), compiled.params))
        return FakeResult(self.rows)


class FakeSessions:
    def __init__(self, session: FakeSession) -> None:
        self.session = session

    @contextmanager
    def begin(self) -> Any:
        yield self.session

    @contextmanager
    def __call__(self) -> Any:
        yield self.session


def _store(rows: list[Any] | None = None) -> tuple[InvestigationStore, FakeSession]:
    session = FakeSession(rows)
    return InvestigationStore(FakeSessions(session)), session  # type: ignore[arg-type]


def test_start_resets_result_and_marks_running() -> None:
    store, session = _store()
    store.start(uuid4(), uuid4(), uuid4())
    assert "ON CONFLICT (incident_id) DO UPDATE" in session.calls[0][0]
    assert session.calls[1][1]["state"] == IncidentState.RUNNING.value


def test_record_agent_merges_json() -> None:
    store, session = _store()
    store.record_agent(uuid4(), "logs", AgentRun(status="failed", error="boom"))
    sql, params = session.calls[0]
    assert "agent_runs || CAST(" in sql
    (entry,) = (value for value in params.values() if isinstance(value, dict))
    assert entry["logs"]["error"] == "boom"


def test_fail_stores_error_and_marks_failed() -> None:
    store, session = _store()
    store.fail(uuid4(), "kaput")
    params = session.calls[0][1]
    assert params["error"] == "kaput"
    assert params["scope"] is None
    assert params["evidence"] == []
    assert session.calls[1][1]["state"] == IncidentState.FAILED.value


def test_get_returns_none_when_not_owned() -> None:
    store, _ = _store()
    assert store.get(uuid4(), uuid4()) is None


def test_get_builds_detail_without_result() -> None:
    now = datetime.now(UTC)
    incident = Incident(
        id=uuid4(),
        run_id=uuid4(),
        user_id=uuid4(),
        service_id="checkout",
        symptom="5xx",
        severity="high",
        window_start=now,
        window_end=now,
        trace_id=None,
        state="CREATED",
        created_at=now,
        updated_at=now,
    )
    store, _ = _store([(incident, None)])
    detail = store.get(uuid4(), uuid4())
    assert detail is not None
    assert detail.incident.service_id == "checkout"
    assert detail.result is None


def test_get_builds_detail_with_result() -> None:
    now = datetime.now(UTC)
    incident_id = uuid4()
    incident = Incident(
        id=incident_id, run_id=uuid4(), user_id=uuid4(), service_id="checkout",
        symptom="5xx", severity="high", window_start=now, window_end=now, trace_id=None,
        state="FAILED", created_at=now, updated_at=now,
    )  # fmt: skip
    result = InvestigationResultRow(
        incident_id=incident_id, run_id=incident.run_id, scope=None, findings=[], evidence=[],
        hypotheses=[], agent_runs={}, error="kaput", started_at=now, finished_at=now,
    )  # fmt: skip
    store, _ = _store([(incident, result)])
    detail = store.get(uuid4(), incident_id)
    assert detail is not None and detail.result is not None
    assert detail.result.error == "kaput"


def test_fail_stale_runs_counts_rows() -> None:
    rows = [(uuid4(), uuid4(), uuid4()) for _ in range(2)]
    store, session = _store(rows)
    assert store.fail_stale_runs() == 2
    assert session.calls[1][1]["error"] == INTERRUPTED_ERROR
