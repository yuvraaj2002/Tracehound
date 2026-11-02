"""Incident reads and writes against PostgreSQL."""

from uuid import UUID, uuid4

from sqlalchemy import select, text, tuple_

from tracehound.db import SessionFactory
from tracehound.helpers.pagination import decode_cursor, encode_cursor
from tracehound.models import Incident
from tracehound.schemas import (
    IncidentAccepted,
    IncidentCreateRequest,
    IncidentListQuery,
    IncidentPage,
    IncidentRecord,
    IncidentStats,
    IncidentStatsQuery,
    Severity,
)

# One round trip for every dashboard figure. Kept as SQL text: generate_series, FILTER and the
# nested json_agg calls read far more clearly here than as SQLAlchemy expressions. `scoped` is
# the user's incidents in [from, to); the previous period [prev_from, from) only needs a count.
# Days are UTC calendar days.
_STATS_SQL = text("""
WITH scoped AS (
    SELECT severity, service_id, state, created_at, window_start, window_end, trace_id
    FROM incidents
    WHERE user_id = :user_id AND created_at >= :from AND created_at < :to
),
days AS (
    SELECT day::date AS day
    FROM generate_series(
        date_trunc('day', :from AT TIME ZONE 'UTC'),
        (:to - interval '1 microsecond') AT TIME ZONE 'UTC',
        interval '1 day'
    ) AS day
),
daily AS (
    SELECT (created_at AT TIME ZONE 'UTC')::date AS day,
           count(*) AS total,
           count(*) FILTER (WHERE severity = 'low') AS low,
           count(*) FILTER (WHERE severity = 'medium') AS medium,
           count(*) FILTER (WHERE severity = 'high') AS high,
           count(*) FILTER (WHERE severity = 'critical') AS critical
    FROM scoped
    GROUP BY 1
),
services AS (
    SELECT service_id, count(*) AS count
    FROM scoped
    GROUP BY service_id
    ORDER BY count DESC, service_id
    LIMIT 5
),
states AS (
    SELECT state, count(*) AS count FROM scoped GROUP BY state
)
SELECT
    count(*) AS total,
    count(*) FILTER (WHERE severity = 'low') AS low,
    count(*) FILTER (WHERE severity = 'medium') AS medium,
    count(*) FILTER (WHERE severity = 'high') AS high,
    count(*) FILTER (WHERE severity = 'critical') AS critical,
    avg(extract(epoch FROM window_end - window_start))::float8 AS avg_window_seconds,
    avg((trace_id IS NOT NULL)::int)::float8 AS trace_coverage,
    (
        SELECT count(*) FROM incidents
        WHERE user_id = :user_id AND created_at >= :prev_from AND created_at < :from
    ) AS previous_total,
    (
        SELECT coalesce(json_object_agg(state, count), '{}'::json) FROM states
    ) AS by_state,
    (
        SELECT coalesce(
            json_agg(json_build_object('service_id', service_id, 'count', count)
                     ORDER BY count DESC, service_id),
            '[]'::json
        )
        FROM services
    ) AS top_services,
    (
        SELECT json_agg(
            json_build_object(
                'day', days.day,
                'total', coalesce(daily.total, 0),
                'low', coalesce(daily.low, 0),
                'medium', coalesce(daily.medium, 0),
                'high', coalesce(daily.high, 0),
                'critical', coalesce(daily.critical, 0)
            )
            ORDER BY days.day
        )
        FROM days LEFT JOIN daily USING (day)
    ) AS timeseries
FROM scoped
""")


def incident_record(row: Incident) -> IncidentRecord:
    return IncidentRecord(
        id=row.id,
        run_id=row.run_id,
        service_id=row.service_id,
        symptom=row.symptom,
        severity=row.severity,  # type: ignore[arg-type]
        window_start=row.window_start,
        window_end=row.window_end,
        trace_id=row.trace_id,
        state=row.state,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class IncidentHelper:
    """Incident queries through one session factory. Timestamps are stored as `timestamptz`."""

    def __init__(self, sessions: SessionFactory) -> None:
        self._sessions = sessions

    def create(self, user_id: UUID, request: IncidentCreateRequest) -> IncidentAccepted:
        """Insert a new incident owned by `user_id`, in the CREATED state."""
        incident_id, run_id = uuid4(), uuid4()
        with self._sessions.begin() as session:
            session.add(
                Incident(
                    id=incident_id,
                    run_id=run_id,
                    user_id=user_id,
                    service_id=request.service_id,
                    symptom=request.symptom,
                    severity=request.severity.value,
                    window_start=request.window_start,
                    window_end=request.window_end,
                    trace_id=request.trace_id,
                )
            )
        return IncidentAccepted(
            incident_id=incident_id,
            run_id=run_id,
            status_url=f"/v1/incidents/{incident_id}",
        )

    def get(self, user_id: UUID, incident_id: UUID) -> IncidentRecord | None:
        """Return the incident if `user_id` owns it, else None."""
        stmt = select(Incident).where(Incident.id == incident_id, Incident.user_id == user_id)
        with self._sessions() as session:
            row = session.scalars(stmt).first()
        return incident_record(row) if row else None

    def list(self, user_id: UUID, query: IncidentListQuery) -> IncidentPage:
        """One page of `user_id`'s incidents created in ``[from, to)``, newest first.

        `severity`, `state` and `service_id` narrow the page when given; the cursor stays valid
        because filters only drop rows, never reorder them.

        Raises `InvalidCursor` when `query.cursor` is malformed.
        """
        stmt = select(Incident).where(
            Incident.user_id == user_id,
            Incident.created_at >= query.from_,
            Incident.created_at < query.to,
        )
        if query.severity:
            stmt = stmt.where(Incident.severity.in_([s.value for s in query.severity]))
        if query.state:
            stmt = stmt.where(Incident.state.in_(list(query.state)))
        if query.service_id:
            stmt = stmt.where(Incident.service_id == query.service_id)
        if query.cursor:
            stmt = stmt.where(
                tuple_(Incident.created_at, Incident.id) < decode_cursor(query.cursor)
            )
        stmt = stmt.order_by(Incident.created_at.desc(), Incident.id.desc()).limit(query.limit + 1)
        with self._sessions() as session:
            rows = session.scalars(stmt).all()
        items = [incident_record(row) for row in rows[: query.limit]]
        next_cursor = None
        if len(rows) > query.limit:
            next_cursor = encode_cursor(items[-1].created_at, items[-1].id)
        return IncidentPage(items=items, next_cursor=next_cursor)

    def stats(self, user_id: UUID, query: IncidentStatsQuery) -> IncidentStats:
        """Dashboard figures for `user_id`'s incidents created in ``[from, to)``."""
        params = {
            "user_id": user_id,
            "from": query.from_,
            "to": query.to,
            "prev_from": query.from_ - (query.to - query.from_),
        }
        with self._sessions() as session:
            # an aggregate without GROUP BY always returns one row
            row = session.execute(_STATS_SQL, params).mappings().one()
        return IncidentStats(
            from_=query.from_,
            to=query.to,
            total=row["total"],
            previous_total=row["previous_total"],
            by_severity={s.value: row[s.value] for s in Severity},
            by_state=row["by_state"],
            top_services=row["top_services"],
            timeseries=row["timeseries"],
            avg_window_seconds=row["avg_window_seconds"],
            trace_coverage=row["trace_coverage"],
        )
