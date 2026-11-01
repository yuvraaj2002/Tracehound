# Testing integrations against real backends

Today every investigation runs on scenario files (`scenarios/<name>`). This plan replaces them
with real telemetry: run Loki, Prometheus and Tempo locally, send them data from a small app
with a fault we can switch on, add a GitHub repo for deploys, and connect Tracehound to all of
it.

## Where the code is today

| Part | Status |
|---|---|
| Live adapters: `LokiLogSource`, `PrometheusMetricSource`, `TempoTraceSource`, `GitHubDeploySource` (`src/tracehound/tools/*/adapters/`) | Written |
| Connecting an integration through `POST /v1/integrations` | Loki only. `IntegrationKind` lists all four, but `IntegrationCreateRequest.kind` is `Literal["loki"]` (`src/tracehound/schemas/integration.py`) |
| Testing a connection (status `untested` → `active` / `failing`) | No endpoint yet |
| Investigations reading from a user's integrations | Not wired. The worker (`src/tracehound/worker/runner.py`) uses only scenario files. Users not in `FIXTURE_USER_IDS` end FAILED |

A local stack can test the adapters right away, but the full incident → root cause flow
needs steps 3 and 4 below.

## Test setup

### 1. Backends in one container

`grafana/otel-lgtm` runs Loki, Tempo, Prometheus, Grafana and an OpenTelemetry collector
together. Docker Desktop must be running.

Everything runs from `simulation/docker-compose.yml`: the `lgtm` container, an nginx
`auth-proxy` in front of it, Postgres (`orders-db`) and the demo `checkout-api`.

```bash
docker compose -f simulation/docker-compose.yml up -d --build
python3 simulation/traffic.py            # steady traffic, Ctrl+C to stop
curl -X POST localhost:8080/admin/fault   # shrink the DB pool; DELETE to restore
```

Loki, Tempo and Prometheus are reachable only through the proxy, which requires basic auth
with a separate login per backend, like Grafana Cloud. The logins are in
`simulation/nginx/nginx.conf` and in `.env` as `SIM_*` variables.

| Service | URL |
|---|---|
| Grafana UI (to check the data by eye) | http://localhost:3000 |
| Loki | http://localhost:3100 |
| Tempo | http://localhost:3200 |
| Prometheus | http://localhost:9090 |
| OTLP collector (the app sends here) | gRPC `localhost:4317`, HTTP `localhost:4318` |

### 2. A demo app with a fault switch

Empty backends prove nothing, so we need an app that sends real telemetry and can fail on
purpose. The plan is a small FastAPI "checkout" service, instrumented with OpenTelemetry, that
sends logs, metrics and traces to the collector. A flag (e.g. `FAULT=db_pool_exhaustion`)
shrinks its database connection pool so requests time out. This mirrors the existing
`checkout_db_pool_exhaustion` scenario, so we already know the right root cause.

A traffic script sends steady requests, then the fault is switched on. That gives a real
incident with known ground truth.

The official OpenTelemetry Demo is an alternative, but it's large (about 15 services) and its
faults are harder to line up with our ground truth.

### 3. GitHub deploys

Create a throwaway GitHub repo with a simple Actions workflow. Each push to `main` counts as a
deploy. Push a commit just before switching the fault on, so the deploy agent has a suspect to
find.

### 4. Connect Tracehound

Add to `.env`, because the URL check blocks local and non-https addresses by default:

```bash
ALLOW_INSECURE_INTEGRATION_URLS=1
```

Then connect each backend: Loki at `http://localhost:3100`, Prometheus at `:9090`, Tempo at
`:3200`, and the test repo for GitHub. Each uses basic auth with its own `SIM_*_USERNAME` and `SIM_*_PASSWORD` from `.env`.

## Build order

1. **Compose file and demo app.** Add `docker-compose.yml` with the LGTM container, the
   checkout app with its fault flag, and the traffic script.
2. **Adapter check.** Run each live adapter against the stack. This is the first real test that
   our LogQL, PromQL and TraceQL queries and label names (e.g. `service_name`) match real data.
3. **API.** Allow all four kinds in `POST /v1/integrations` and add a test-connection endpoint
   that sets the status to `active` or `failing`.
4. **Worker.** Build the data sources from the user's integrations instead of scenario files,
   then run a full investigation on the live incident and compare it with
   `ground_truth/checkout_db_pool_exhaustion.json`.

## What a passing first-level test looks like

- Each adapter returns data from the stack, with no empty results or query errors.
- Each integration shows `active` after the connection test.
- An investigation started during the fault names the database pool as the root cause and cites
  real log lines, metrics, traces and the deploy.
