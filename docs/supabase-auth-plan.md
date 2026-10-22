# Supabase auth plan

- Status: Draft
- Date: 2026-10-22

## Context

The API has no authentication. `/v1/incidents` accepts and lists incidents for anyone, and
there is no notion of a user or a tenant, although ADR 0005 already assumes `tenant_id` on
integrations.

Supabase is the chosen backend-as-a-service:

- **Auth**: email/password, magic links, OAuth (GitHub, Google), password reset, email
  verification and token refresh, without writing any of it.
- **Postgres**: the PRD already targets Postgres (ADR 0004). Callers depend only on
  `IncidentHelper.create`, `get` and `list_all`, so swapping the store is contained.
- **Vault**: encrypted secrets inside Postgres, enough to back `secret_ref` from ADR 0005
  before adopting a dedicated secrets manager.
- **Storage**: a later home for investigation artifacts, evidence snapshots and reports.

Lock-in is moderate. The database is plain Postgres; the auth coupling in the backend is
limited to JWT verification.

## Decisions

1. **Login happens in the browser, not in FastAPI.** The React UI uses `supabase-js` to sign
   in and receives an access token (JWT). FastAPI only verifies that token on each request.
   There is no `/login` or `/signup` route in the backend.
2. **Asymmetric JWT signing keys (RS256/ES256).** FastAPI verifies tokens with public keys from
   `https://<project>.supabase.co/auth/v1/.well-known/jwks.json`. The backend never holds the
   legacy HS256 shared secret. The JWKS endpoint returns no keys while a project is still on
   HS256, so this must be switched on in the dashboard.
3. **FastAPI enforces tenancy.** All data access goes through the API, and every query filters
   by `tenant_id`. Postgres row-level security (RLS) can be added later as a second layer.
   Note that a service-role or direct Postgres connection bypasses RLS, which is why the
   application check is the primary one.
4. **Supabase owns users; Tracehound owns tenants.** Supabase Auth has no organization model.
   `tenants` and `memberships` are our tables, keyed by the Supabase user UUID (`sub`).
5. **Two kinds of callers.** People authenticate with a Supabase JWT. Machines (Alertmanager,
   PagerDuty, Grafana webhooks) authenticate with tenant-scoped API keys, which Supabase does
   not provide. Both resolve to a `tenant_id`.
6. **SQLite stays for now.** Tenancy tables are added to SQLite first. The move to Supabase
   Postgres is a separate step, so auth and storage don't change at the same time.

## Request flow

```
Browser                Supabase Auth            FastAPI
   | -- sign in ------------> |                    |
   | <-- access + refresh --- |                    |
   | -- GET /v1/incidents, Authorization: Bearer <access> --> |
   |                          | <-- JWKS (cached) ---------- |
   |                          |    verify sig, exp, aud, iss  |
   |                          |    sub -> membership -> tenant_id
   | <------------------- incidents for that tenant -------- |

Webhook (Alertmanager)                           FastAPI
   | -- POST /v1/incidents, Authorization: Bearer th_<key> --> |
   |                          hash(key) -> api_keys -> tenant_id
```

## Implementation phases

### Phase 0: Decision record

Turn the decisions above into ADR 0006 once the plan is settled. ADR 0006 also amends ADR
0004's "no external services locally" rule, since the `supabase` CLI runs the stack in
Docker.

### Phase 1: Supabase project setup (dashboard)

1. Create the project. Under **Auth → Signing Keys**, enable asymmetric keys and confirm the
   JWKS URL returns keys.
2. Enable providers: email/password and GitHub to start.
3. Set the Site URL and redirect URLs (`http://localhost:5173` for Vite dev, production
   domain later).
4. Environment variables:
   - UI: `VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY`
   - API: `SUPABASE_URL`, `SUPABASE_JWKS_URL`
   - The service-role key is not needed yet and must never reach the UI.

### Phase 2: Backend token verification

5. Add `pyjwt[crypto]`. Its `PyJWKClient` fetches and caches JWKS keys.
6. New module `src/tracehound/auth/` with `verify_token(token) -> Principal`:
   - select the key by the token's `kid` and verify the signature
   - check `exp`, `aud == "authenticated"`, `iss == f"{SUPABASE_URL}/auth/v1"`
   - return `Principal(user_id=sub, email=email)`
7. `CurrentPrincipalDep` in `api/dependencies.py`, next to `IncidentHelperDep`: reads
   `Authorization: Bearer ...`, calls `verify_token`, raises 401 on any failure.
8. Protect `/v1/incidents`. Keep `/health` public.

After this phase any signed-in user sees every incident; Phase 3 closes that.

### Phase 3: Tenancy

9. Tables:

   ```
   tenants
     id            uuid
     name          text
     created_at

   memberships
     user_id       uuid            -- Supabase auth user (JWT sub)
     tenant_id     uuid
     role          'owner' | 'admin' | 'member'
     created_at
     primary key (user_id, tenant_id)

   incidents
     + tenant_id   uuid            -- required on every row
   ```

10. Dependency that resolves `Principal -> tenant_id` from memberships, using an
    `X-Tenant-Id` header when the user belongs to several tenants (403 if they are not a
    member). `tenant_id` is passed into every `IncidentHelper` call; a query without a
    tenant filter is a bug.
11. Bootstrap routes:
    - `GET /v1/me`: the user and their tenants.
    - `POST /v1/tenants`: create a tenant with the caller as owner (first sign-in).

If accounts are single-person, memberships collapses to a `tenant_id` per user and roles are
dropped. (Open question below.)

### Phase 4: Machine access (API keys)

12. Table:

    ```
    api_keys
      id            uuid
      tenant_id     uuid
      name          text
      prefix        text            -- first characters, shown in the UI to identify the key
      key_hash      text            -- SHA-256 of the key; the key itself is never stored
      created_by    uuid
      last_used_at, revoked_at, created_at
    ```

13. Routes: `POST /v1/api-keys` (returns the full key once), `GET /v1/api-keys`,
    `DELETE /v1/api-keys/{id}` (sets `revoked_at`).
14. The auth dependency accepts either a Supabase JWT or an API key (distinguished by a
    `th_` prefix) and resolves both to `tenant_id`.

### Phase 5: Frontend

15. Add `@supabase/supabase-js`, a sign-in page and session handling (the client refreshes
    tokens itself), plus a fetch wrapper that attaches `Authorization: Bearer <access_token>`.
16. Gate app routes on a session; add a tenant switcher if multi-membership is supported.

### Phase 6: Tests and hardening

17. Tests sign tokens with a locally generated keypair and point the JWKS client at it, so no
    test calls Supabase. Cases: valid, expired, wrong audience, wrong issuer, tampered,
    missing header, revoked API key, and tenant isolation (user A cannot read tenant B).
18. Restrict CORS to the UI origin, keep tokens and API keys out of logs, rate-limit
    API-key intake.

## API surface after all phases

| Method | Path                    | Caller          | Purpose                         |
| ------ | ----------------------- | --------------- | ------------------------------- |
| GET    | `/health`               | anyone          | liveness                        |
| GET    | `/v1/me`                | user            | current user and tenants        |
| POST   | `/v1/tenants`           | user            | create tenant, caller is owner  |
| POST   | `/v1/incidents`         | user or API key | incident intake                 |
| GET    | `/v1/incidents`         | user            | list the tenant's incidents     |
| POST   | `/v1/api-keys`          | user (admin)    | create key, shown once          |
| GET    | `/v1/api-keys`          | user (admin)    | list keys (prefix only)         |
| DELETE | `/v1/api-keys/{id}`     | user (admin)    | revoke key                      |

Sign-up, sign-in, sign-out, password reset and OAuth callbacks are Supabase endpoints called
by the UI, not routes in this API.

## Open questions

- Is a Tracehound account one person, or a team with invites and roles? This decides whether
  Phase 3 needs memberships and an invite flow.
- When does storage move from SQLite to Supabase Postgres, and does RLS get added then?
