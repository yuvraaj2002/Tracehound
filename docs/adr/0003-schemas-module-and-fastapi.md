# ADR 0003: Rename `domain` to `schemas`; adopt FastAPI for the API layer

- Status: Accepted
- Date: 2026-10-17

## Context

The `domain` module only holds typed Pydantic contracts, so `schemas` describes it better.
The intake endpoint (`POST /v1/incidents`) is the first piece of the API layer.

## Decision

- Rename `tracehound.domain` to `tracehound.schemas`. Dependency rules from ADR 0002 are
  unchanged.
- Use FastAPI for `tracehound.api`. The request/response models
  (`IncidentCreateRequest`, `IncidentAccepted`) and shared types like `Severity` live in
  `schemas/incident.py`, so the API layer holds only routing.
- `httpx` is a dev dependency, used by FastAPI's test client.

## Consequences

`fastapi` is imported only from `tracehound.api`. `schemas` still imports no framework.
