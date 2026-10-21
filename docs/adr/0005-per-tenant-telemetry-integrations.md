# ADR 0005: Per-tenant telemetry integrations

- Status: Proposed
- Date: 2026-10-21

## Context

Specialists read telemetry through adapters (`LogSource` in `tools/logs/`: `FileLogSource`,
`LokiLogSource`, with CloudWatch and Elasticsearch stubbed). In production each customer
uses their own backend, with their own URL, field names and credentials. A run needs to know
which backend to call and how to authenticate, without that leaking into the agents.

This is the standard multi-tenant "integrations" pattern: Grafana data sources, Datadog
integrations and Airbyte connections all store one record per customer per backend and
resolve it at run time.

## Decision

Store one integration record per tenant per backend, and build the adapter from it when a run
starts.

```
integrations
  id            uuid
  tenant_id     uuid            -- which customer
  kind          'loki' | 'cloudwatch' | 'elasticsearch'
  config        jsonb           -- non-secret: url, region, service_label, field mapping
  secret_ref    text            -- pointer to the credential, never the credential itself
  status        'active' | 'failing'
  last_tested_at, created_at, updated_at
```

Run time:

```
run starts -> load integration for tenant -> fetch secret via secret_ref
           -> make_log_source(kind, config, secret) -> LokiLogSource(...) -> LogsAgent
```

Rules:

- **Secrets out of the main table.** Keep credentials in a secrets manager (AWS Secrets
  Manager, Vault, GCP Secret Manager) and store only the reference. At minimum, encrypt the
  column with a KMS-managed key.
- **Prefer keyless auth.** For AWS, the customer creates an IAM role that Tracehound assumes
  with an external ID, so no access keys are shared. For Grafana Cloud, use a read-only
  service-account token.
- **Read-only scopes.** Request query permissions only.
- **Test connection on save.** Run a small query before marking an integration `active`, so
  broken setups fail at configuration time, not mid-incident.
- **Record what a run used.** Store the integration id and version on the run so results
  stay traceable after the config changes.
- **Secrets stay in the adapter.** Credentials go into the adapter's HTTP client only; never
  into agent context, LangGraph state, checkpoints or logs.

The factory takes a plain config object. Whether it comes from a YAML file (local runs and
scenarios) or this table (production) is a loader detail, so the database can be added later
without changing adapters or agents.

## Consequences

- Loki is the first real backend (Grafana-first); other kinds are added as new adapters plus
  one factory case.
- Needs a secrets manager or KMS dependency before multi-tenant production use.
- Evidence locators must come from the adapter (e.g. Loki labels and timestamp) rather than
  `logs.json#id`.
- Until the table exists, local config (YAML or env vars) feeds the same factory.
