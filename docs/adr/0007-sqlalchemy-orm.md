# ADR 0007: SQLAlchemy ORM for database access

- Status: Accepted
- Date: 2026-11-02
- Amends: ADR 0006 (driver and access layer)

## Context

The helpers in `tracehound.helpers` built SQL strings by hand and ran them on a psycopg pool.
The tables existed only in `supabase/migrations`, so nothing in Python described them, and a
renamed column broke queries silently until a test hit them.

## Decision

- **ORM:** SQLAlchemy 2 with typed declarative models (`Mapped[...]`), one class per table in
  `tracehound.models`. psycopg 3 stays as the driver (`postgresql+psycopg://`).
- **Schema ownership:** the SQL files in `supabase/migrations` stay the source of truth. Supabase
  records them, and they hold Postgres-only details (RLS, `auth.users` references). Models mirror
  the migrations; we don't use Alembic or `create_all`. `tests/integration/test_models_match_migrations.py`
  fails when the two drift.
- **Sessions:** `create_app` builds one `Engine` (pool of 5, prepared statements off for the
  transaction pooler) and a `sessionmaker`. Helpers take the session factory and open a
  session per call: `sessions.begin()` for writes, `sessions()` for reads.
- **Escape hatch:** the incident stats query stays SQL text through `sqlalchemy.text()`, since
  `generate_series`, `FILTER` and nested `json_agg` read better as SQL. Upserts use the
  PostgreSQL `insert(...).on_conflict_do_update`.
- **Naming:** ORM classes whose name would clash with an API schema end in `Row`
  (`InvestigationResultRow`, `ServiceCatalogRow`).

## Consequences

A schema change now needs a migration and a matching model edit. Helpers convert ORM objects to
Pydantic schemas explicitly, so the API contract stays separate from the table layout.
