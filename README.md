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
  db/            local SQLite setup: connections, schema
  helpers/       per-entity DB queries (incident_helper, ...)
  api/           HTTP API
simulation/      synthetic services that generate seeded faults
fixtures/        pinned telemetry snapshots per scenario
benchmarks/      ground-truth annotations (never shown to agents)
docs/adr/        architecture decision records
tests/           unit and integration tests
```

## Development

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12+.

```bash
uv sync                 # create .venv and install dependencies
uv run pytest           # run tests
uv run ruff check       # lint
uv run ruff format      # format
```
