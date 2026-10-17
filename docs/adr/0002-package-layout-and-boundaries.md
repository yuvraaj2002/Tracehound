# ADR 0002: Package layout and module boundaries

- Status: Accepted (the `domain` module was renamed `schemas` in ADR 0003)
- Date: 2026-10-17

## Context

The PRD asks for domain contracts (the `schemas` module) and tools that stay framework-agnostic (LangGraph, FastAPI,
AWS are replaceable), and for ground-truth annotations that never reach agent context.

## Decision

Use a `src/` layout managed by `uv`, with one package `tracehound` split into:

| Module         | Responsibility                                              | May depend on            |
|----------------|-------------------------------------------------------------|--------------------------|
| `schemas`      | Pydantic contracts, states, invariants                      | nothing internal         |
| `tools`        | Read-only telemetry interfaces and adapters                 | `schemas`                |
| `agents`       | Specialist agents                                           | `schemas`, `tools`       |
| `orchestrator` | Workflow state machine, budgets, checkpoints                | `schemas`, `agents`      |
| `db`           | Local SQLite setup: connections, schema                     | nothing internal         |
| `helpers`      | Per-entity DB queries (`incident_helper`, ...)              | `schemas`, `db`          |
| `api`          | HTTP layer                                                  | everything above         |

Outside the package:

- `simulation/` — synthetic microservices and fault toggles that generate telemetry.
- `fixtures/scenarios/` — pinned telemetry snapshots that agents may read.
- `benchmarks/ground_truth/` — causal annotations, read only by the evaluator.

## Consequences

`schemas` stays importable without any framework installed. Framework dependencies are added
only to the module that needs them, when it is built.
