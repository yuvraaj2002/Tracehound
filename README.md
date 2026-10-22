# Tracehound

Evidence-first multi-agent incident investigation for Python services. Given an alert, it
gathers logs, metrics and deployment evidence, tests competing root-cause hypotheses, and
produces an auditable, cited incident report.

> Status: early scaffolding (PRD roadmap, week 1).

## Layout

```
src/tracehound/
  schemas/       typed contracts: incidents, evidence, hypotheses, states
  tools/         read-only telemetry interfaces and adapters
  agents/        specialist agents
  orchestrator/  workflow state machine, budgets, checkpoints
  db/            PostgreSQL connection pool
  helpers/       per-entity DB queries (incident_helper, ...)
  api/           HTTP API
simulation/      synthetic services that generate seeded faults
scenarios/       pinned telemetry per scenario (what agents may read)
ground_truth/    root-cause answers per scenario (never shown to agents)
supabase/        database migrations (applied to the Supabase project)
docs/adr/        architecture decision records
tests/           unit and integration tests
```

## Development

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12+.

```bash
uv sync                 # create .venv and install dependencies
uv run pytest           # run tests (database tests need DATABASE_URL)
uv run ruff check       # lint
uv run ruff format      # format
```

### Database

Incidents are stored in PostgreSQL on Supabase. Put the connection string in `.env`:

```bash
DATABASE_URL=postgresql://postgres.<project-ref>:<password>@<region>.pooler.supabase.com:5432/postgres
```

Use the **Session pooler** string from the dashboard's Connect panel; the direct
`db.<ref>.supabase.co` host is IPv6-only. Schema changes go in `supabase/migrations/` as
timestamped SQL files. The database tests in `tests/integration/test_incident_db.py` build each
migration into a throwaway schema and drop it afterwards.

```bash
uv run uvicorn tracehound.api.app:create_app --factory
```
