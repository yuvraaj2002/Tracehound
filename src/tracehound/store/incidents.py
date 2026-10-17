"""SQLite-backed incident persistence."""

import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from tracehound.schemas import IncidentAccepted, IncidentCreateRequest

_SCHEMA = """
CREATE TABLE IF NOT EXISTS incidents (
    id           TEXT PRIMARY KEY,
    run_id       TEXT NOT NULL,
    service_id   TEXT NOT NULL,
    symptom      TEXT NOT NULL,
    severity     TEXT NOT NULL,
    window_start TEXT NOT NULL,
    window_end   TEXT NOT NULL,
    trace_id     TEXT,
    state        TEXT NOT NULL DEFAULT 'CREATED',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
)
"""


class IncidentStore:
    """Stores incidents in a local SQLite file. Timestamps are ISO-8601 UTC strings."""

    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        return conn

    def create(self, request: IncidentCreateRequest) -> IncidentAccepted:
        incident_id, run_id = uuid4(), uuid4()
        now = datetime.now(UTC).isoformat()
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO incidents (id, run_id, service_id, symptom, severity, window_start,"
                " window_end, trace_id, state, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'CREATED', ?, ?)",
                (
                    str(incident_id),
                    str(run_id),
                    request.service_id,
                    request.symptom,
                    request.severity.value,
                    request.window_start.isoformat(),
                    request.window_end.isoformat(),
                    request.trace_id,
                    now,
                    now,
                ),
            )
        return IncidentAccepted(
            incident_id=incident_id,
            run_id=run_id,
            status_url=f"/v1/incidents/{incident_id}",
        )

    def get(self, incident_id: UUID) -> dict[str, str | None] | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM incidents WHERE id = ?", (str(incident_id),)
            ).fetchone()
        return dict(row) if row else None
