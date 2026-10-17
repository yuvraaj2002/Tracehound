"""Incident reads and writes against the local SQLite database."""

from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from tracehound.db import connect
from tracehound.schemas import IncidentAccepted, IncidentCreateRequest, IncidentRecord


class IncidentHelper:
    """Incident queries for one SQLite file. Timestamps are stored as ISO-8601 UTC strings."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def create(self, request: IncidentCreateRequest) -> IncidentAccepted:
        """Insert a new incident in the CREATED state."""
        incident_id, run_id = uuid4(), uuid4()
        now = datetime.now(UTC).isoformat()
        with closing(connect(self._db_path)) as conn, conn:
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

    def get(self, incident_id: UUID) -> IncidentRecord | None:
        with closing(connect(self._db_path)) as conn:
            row = conn.execute(
                "SELECT * FROM incidents WHERE id = ?", (str(incident_id),)
            ).fetchone()
        return IncidentRecord.model_validate(dict(row)) if row else None

    def list_all(self) -> list[IncidentRecord]:
        """Return every incident, newest first."""
        with closing(connect(self._db_path)) as conn:
            rows = conn.execute("SELECT * FROM incidents ORDER BY created_at DESC").fetchall()
        return [IncidentRecord.model_validate(dict(row)) for row in rows]
