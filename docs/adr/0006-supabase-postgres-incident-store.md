# ADR 0006: Supabase PostgreSQL for incident persistence

- Status: Accepted
- Date: 2026-10-22
- Supersedes: ADR 0004

## Context

ADR 0004 used local SQLite until the PRD's PostgreSQL target was needed. A Supabase project
now exists for auth (`docs/supabase-auth-plan.md`), and every Supabase project is a Postgres
database, so storage moves there now instead of after auth.

## Decision

- **Driver:** psycopg 3 with `psycopg_pool`. `tracehound.db.create_pool` opens a pool of up
  to 5 connections on `DATABASE_URL`. Rows come back as dicts. Server-side prepared statements
  are off so the transaction pooler also works.
- **Lifecycle:** `create_app` opens the pool in the FastAPI lifespan and closes it on
  shutdown. It takes a `pool_factory` so tests can supply their own pool.
- **Schema:** SQL migrations in `supabase/migrations/`, named with the version Supabase
  records. The app no longer creates tables at startup.
- **Types:** `uuid` ids and `timestamptz` timestamps replace SQLite's text columns. Severity
  and window order are also enforced by check constraints.
- **Access:** RLS is enabled on `incidents` with no policies, so the anon and authenticated
  roles can't reach it through Supabase's public API. The backend connects as the database
  owner and bypasses RLS. Per-tenant policies come with the tenancy work.
- **Tests:** API tests use an in-memory helper and need no database. Real-database tests are
  marked `integration`. Each one builds the migrations into a throwaway schema and drops it
  afterwards.

## Consequences

Local development needs network access and a `DATABASE_URL`; there is no offline store. The
direct `db.<ref>.supabase.co` host is IPv6-only, so most networks need the Session pooler
string. Callers still depend only on `IncidentHelper.create`, `get` and `list_all`.
