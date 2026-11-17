# ADR 0001: Record architecture decisions

- Status: Accepted
- Date: 2026-10-17

## Context

The PRD requires published ADRs, and several early choices (framework boundaries, storage,
model access) will be revisited when benchmarks come in. Decisions need to be traceable.

## Decision

Record significant decisions as numbered Markdown files in `docs/adr/`, using
Context / Decision / Consequences. Superseded ADRs are kept and marked as such.

## Consequences

Each structural change (new dependency, new boundary, new store) gets a short ADR in the
same PR that introduces it.
