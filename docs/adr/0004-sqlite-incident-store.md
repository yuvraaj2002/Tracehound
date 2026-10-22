# ADR 0004: SQLite for local incident persistence

- Status: Superseded by ADR 0006
- Date: 2026-10-17

## Context

Incident intake needs durable storage. The PRD targets PostgreSQL eventually, but the local
phase should run with no external services.

## Decision

Use stdlib `sqlite3`. `tracehound.db.setup` owns connections and schema creation
(`connect`, `init_db`); incident queries live in `tracehound.helpers.incident_helper.IncidentHelper`. Data goes to
`data/tracehound.db` (override with `TRACEHOUND_DB_PATH`). The `incidents` table holds the
intake fields plus `run_id`, `state`, `created_at` and `updated_at`. Timestamps are ISO-8601
UTC text. `uvicorn` is added to serve the API.

## Consequences

No new ORM dependency. Moving to PostgreSQL later means replacing `db.setup` and the helper
modules; callers depend only on
`IncidentHelper.create`, `get` and `list_all`. `run_id` lives on `incidents` for now and moves to an
`investigation_runs` table when runs are built.
