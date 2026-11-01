from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from tracehound.helpers.investigation_helper import INTERRUPTED_ERROR, InvestigationStore
from tracehound.schemas import AgentRun, IncidentState


class FakeConn:
    """Records every statement; returns the queued rows for the next fetch."""

    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.calls: list[tuple[str, Any]] = []
        self.rows = rows or []

    def execute(self, sql: str, params: Any = None) -> "FakeConn":
        self.calls.append((sql, params))
        return self

    def fetchone(self) -> dict[str, Any] | None:
        return self.rows[0] if self.rows else None

    def fetchall(self) -> list[dict[str, Any]]:
        return self.rows

    @contextmanager
    def transaction(self) -> Any:
        yield


class FakePool:
    def __init__(self, conn: FakeConn) -> None:
        self.conn = conn

    @contextmanager
    def connection(self) -> Any:
        yield self.conn


def _store(rows: list[dict[str, Any]] | None = None) -> tuple[InvestigationStore, FakeConn]:
    conn = FakeConn(rows)
    return InvestigationStore(FakePool(conn)), conn  # type: ignore[arg-type]


def test_start_resets_result_and_marks_running() -> None:
    store, conn = _store()
    store.start(uuid4(), uuid4(), uuid4())
    assert "ON CONFLICT" in conn.calls[0][0]
    assert conn.calls[1][1][0] == IncidentState.RUNNING.value


def test_record_agent_merges_json() -> None:
    store, conn = _store()
    store.record_agent(uuid4(), "logs", AgentRun(status="failed", error="boom"))
    sql, params = conn.calls[0]
    assert "agent_runs ||" in sql
    assert params[0] == "logs"
    assert params[1].obj["error"] == "boom"


def test_fail_stores_error_and_marks_failed() -> None:
    store, conn = _store()
    store.fail(uuid4(), "kaput")
    params = conn.calls[0][1]
    assert params["error"] == "kaput"
    assert params["scope"] is None
    assert params["evidence"].obj == []
    assert conn.calls[1][1][0] == IncidentState.FAILED.value


def test_get_returns_none_when_not_owned() -> None:
    store, _ = _store()
    assert store.get(uuid4(), uuid4()) is None


def test_get_builds_detail_without_result() -> None:
    now = datetime.now(UTC).isoformat()
    incident = {
        "id": str(uuid4()),
        "run_id": str(uuid4()),
        "user_id": str(uuid4()),
        "service_id": "checkout",
        "symptom": "5xx",
        "severity": "high",
        "window_start": now,
        "window_end": now,
        "trace_id": None,
        "state": "CREATED",
        "created_at": now,
        "updated_at": now,
    }
    store, _ = _store([{"incident": incident, "result": None}])
    detail = store.get(uuid4(), uuid4())
    assert detail is not None
    assert detail.incident.service_id == "checkout"
    assert detail.result is None


def test_fail_stale_runs_counts_rows() -> None:
    rows = [{"id": uuid4(), "user_id": uuid4(), "run_id": uuid4()} for _ in range(2)]
    store, conn = _store(rows)
    assert store.fail_stale_runs() == 2
    assert conn.calls[1][1][3] == INTERRUPTED_ERROR
