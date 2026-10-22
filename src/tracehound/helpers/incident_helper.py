"""Incident reads and writes against PostgreSQL."""

from uuid import UUID, uuid4

from psycopg_pool import ConnectionPool

from tracehound.schemas import IncidentAccepted, IncidentCreateRequest, IncidentRecord


class IncidentHelper:
    """Incident queries over one connection pool. Timestamps are stored as `timestamptz`."""

    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def create(self, request: IncidentCreateRequest) -> IncidentAccepted:
        """Insert a new incident in the CREATED state."""
        incident_id, run_id = uuid4(), uuid4()
        with self._pool.connection() as conn:
            conn.execute(
                "INSERT INTO incidents (id, run_id, service_id, symptom, severity, window_start,"
                " window_end, trace_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    incident_id,
                    run_id,
                    request.service_id,
                    request.symptom,
                    request.severity.value,
                    request.window_start,
                    request.window_end,
                    request.trace_id,
                ),
            )
        return IncidentAccepted(
            incident_id=incident_id,
            run_id=run_id,
            status_url=f"/v1/incidents/{incident_id}",
        )

    def get(self, incident_id: UUID) -> IncidentRecord | None:
        with self._pool.connection() as conn:
            row = conn.execute("SELECT * FROM incidents WHERE id = %s", (incident_id,)).fetchone()
        return IncidentRecord.model_validate(row) if row else None

    def list_all(self) -> list[IncidentRecord]:
        """Return every incident, newest first."""
        with self._pool.connection() as conn:
            rows = conn.execute("SELECT * FROM incidents ORDER BY created_at DESC").fetchall()
        return [IncidentRecord.model_validate(row) for row in rows]
