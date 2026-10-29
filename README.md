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

The API allows browser calls from the origins in `CORS_ORIGINS` (comma-separated, default
`http://localhost:5173`).

### Integrations

Users connect their own telemetry backends (Loki first) with `POST /v1/integrations`. The
credential is encrypted with AES-256-GCM before it reaches the database, using a 32-byte key in
`.env`:

```bash
INTEGRATION_ENCRYPTION_KEY=$(python -c 'import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())')
```

Losing this key makes every stored credential unreadable. Backend URLs must be https and must not
point at private addresses; set `ALLOW_INSECURE_INTEGRATION_URLS=1` locally to allow
`http://localhost:3100` and similar.

### Authentication (UI)

The UI in `ui/` signs users in with Google or GitHub through Supabase Auth (PKCE flow) and sends
the session's access token as `Authorization: Bearer <token>` on every API call. Put these in
`ui/.env.local` (see `ui/.env.example`):

```bash
VITE_SUPABASE_URL=https://<project-ref>.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=sb_publishable_...
VITE_API_URL=http://localhost:8000
```

```bash
cd ui && npm ci && npm run dev   # http://localhost:5173
```

Routes: `/` landing, `/signin`, `/auth/callback` (finishes the OAuth redirect) and `/app`
(signed-in only).

One-time setup in the Supabase dashboard:

1. **Auth → Providers**: enable Google and GitHub with each provider's OAuth client ID and secret.
   In the Google Cloud and GitHub OAuth apps, set the authorized callback URL to
   `https://gtokkvxmjzyutqvohlqq.supabase.co/auth/v1/callback`.
2. **Auth → URL Configuration**: set Site URL to `http://localhost:5173` and add
   `http://localhost:5173/auth/callback` to Redirect URLs.
