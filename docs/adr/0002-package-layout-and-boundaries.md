# ADR 0002: Package layout and module boundaries

- Status: Accepted
- Date: 2026-10-17

## Context

The PRD asks for domain contracts and tools that stay framework-agnostic (LangGraph, FastAPI,
AWS are replaceable), and for ground-truth annotations that never reach agent context.

## Decision

Use a `src/` layout managed by `uv`, with one package `tracehound` split into:

| Module         | Responsibility                                              | May depend on            |
|----------------|-------------------------------------------------------------|--------------------------|
| `domain`       | Pydantic contracts, states, invariants                      | nothing internal         |
| `tools`        | Read-only telemetry interfaces and adapters                 | `domain`                 |
| `agents`       | Specialist agents                                           | `domain`, `tools`        |
| `orchestrator` | Workflow state machine, budgets, checkpoints                | `domain`, `agents`       |
| `store`        | Persistence                                                 | `domain`                 |
| `api`          | HTTP layer                                                  | everything above         |

Outside the package:

- `simulation/` — synthetic microservices and fault toggles that generate telemetry.
- `fixtures/scenarios/` — pinned telemetry snapshots that agents may read.
- `benchmarks/ground_truth/` — causal annotations, read only by the evaluator.

## Consequences

`domain` stays importable without any framework installed. Framework dependencies are added
only to the module that needs them, when it is built.
