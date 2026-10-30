"""Incident reads and writes against PostgreSQL."""

from uuid import UUID, uuid4

from psycopg_pool import ConnectionPool

from tracehound.helpers.pagination import decode_cursor, encode_cursor
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

# One round trip for every dashboard figure. `scoped` is the user's incidents in [from, to);
# the previous period [prev_from, from) only needs a count. Days are UTC calendar days.
_STATS_SQL = """
WITH scoped AS (
    SELECT severity, service_id, state, created_at, window_start, window_end, trace_id
    FROM incidents
    WHERE user_id = %(user_id)s AND created_at >= %(from)s AND created_at < %(to)s
),
days AS (
    SELECT day::date AS day
    FROM generate_series(
        date_trunc('day', %(from)s AT TIME ZONE 'UTC'),
        (%(to)s - interval '1 microsecond') AT TIME ZONE 'UTC',
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
        WHERE user_id = %(user_id)s AND created_at >= %(prev_from)s AND created_at < %(from)s
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
"""


class IncidentHelper:
    """Incident queries over one connection pool. Timestamps are stored as `timestamptz`."""

    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def create(self, user_id: UUID, request: IncidentCreateRequest) -> IncidentAccepted:
        """Insert a new incident owned by `user_id`, in the CREATED state."""
        incident_id, run_id = uuid4(), uuid4()
        with self._pool.connection() as conn:
            conn.execute(
                "INSERT INTO incidents (id, run_id, user_id, service_id, symptom, severity,"
                " window_start, window_end, trace_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    incident_id,
                    run_id,
                    user_id,
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

    def get(self, user_id: UUID, incident_id: UUID) -> IncidentRecord | None:
        """Return the incident if `user_id` owns it, else None."""
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT * FROM incidents WHERE id = %s AND user_id = %s", (incident_id, user_id)
            ).fetchone()
        return IncidentRecord.model_validate(row) if row else None

    def list(self, user_id: UUID, query: IncidentListQuery) -> IncidentPage:
        """One page of `user_id`'s incidents created in ``[from, to)``, newest first.

        Raises `InvalidCursor` when `query.cursor` is malformed.
        """
        sql = "SELECT * FROM incidents WHERE user_id = %s AND created_at >= %s AND created_at < %s"
        params: list[object] = [user_id, query.from_, query.to]
        if query.cursor:
            sql += " AND (created_at, id) < (%s, %s)"
            params.extend(decode_cursor(query.cursor))
        sql += " ORDER BY created_at DESC, id DESC LIMIT %s"
        params.append(query.limit + 1)
        with self._pool.connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        items = [IncidentRecord.model_validate(row) for row in rows[: query.limit]]
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
        with self._pool.connection() as conn:
            row = conn.execute(_STATS_SQL, params).fetchone()
        assert row is not None  # an aggregate without GROUP BY always returns one row
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
