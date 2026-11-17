# Loki log fetch — Stage A funnel (implementation checklist)

Status: **design → implement** — track progress with the checkboxes below.

Related:

- Current adapter: `src/tracehound/tools/logs/adapters/loki.py`
- Dedupe helper: `src/tracehound/tools/logs/dedupe.py`
- Agent: `src/tracehound/agents/logs/agent.py`
- Downstream LLM budget (later): `docs/logs-llm-context-budget.md`
- Integrations ADR: `docs/adr/0005-per-tenant-telemetry-integrations.md`

## Goal

Pull a **bounded, failure-biased** set of log lines for Triage-scoped services and the change→symptom window — enough for downstream evidence, not a full dump.

```text
triage → LogsAgent → LogSource.fetch(services, start, end)
                   → Stage A: narrow at Loki (this doc)
                   → Stage B: compress / cluster (later)
                   → Stage C: rank + LLM budget (see logs-llm-context-budget.md)
```

---

## Locked v1 decisions

- [x] Both inclusion lanes: structured WARN/ERROR **and** soft keyword matches on other lines
- [x] Hard cap via Loki `limit` (default **2000**)
- [x] Newest-biased fetch (`direction=backward`), then sort oldest→newest in Tracehound
- [x] Elastic stays stubbed; same `LogSource.fetch` contract later
- [ ] Keyword list finalized (see open items)
- [x] Soft-lane keyword set documented in code + this doc

---

## Funnel overview

| Stage | What | Where | Status |
| --- | --- | --- | --- |
| A | Scope + dual-lane filter + limit at Loki | `LokiLogSource` | In progress |
| B | Near-duplicate compress (template / fingerprint) | `tools/logs/` (not Loki) | Pending |
| C | Rank + top-K / token budget for LLM | Logs agent / context packer | Pending (see other doc) |

---

## Stage A — Fetch at Loki

### A0. Inputs (always)

- [x] Confirm fetch inputs stay: Triage `logs` task `services`, `change_window_start`, `symptom_window_end`
- [x] Empty `services` → return `[]` (no Loki call)
- [x] Inclusive end window behavior documented and tested (Loki end exclusive → nudge)

### A1. Hard lane — structured severity

- [x] Keep lines where structured level ∈ `{WARN, ERROR}` (map FATAL/CRITICAL → ERROR if present)
- [x] Prefer label / parsed JSON level when available (not “message happens to say error”)
- [x] Document how level is matched in LogQL for Grafana JSON / OTel-style streams
- [x] Unit tests: WARN/ERROR kept; plain INFO without keywords dropped by this lane alone

**How level is matched (v1):**

Modern Loki (`discover_log_levels`, default **on**) writes structured metadata `detected_level`
at ingest from JSON / logfmt / OTel fields (`level`, `severity`, …), normalized to lowercase
`trace|debug|info|warn|error|critical|fatal`. That metadata is **not** a stream label, so it
must be filtered in the pipeline (not inside `{…}`):

```logql
{service_name=~`a|b`} | detected_level=~`warn|error|fatal|critical`
```

Bloom acceleration prefers this filter **before** any `| json` / `| logfmt` parser stage.
Tracehound maps `fatal`/`critical` → `LogLine.level=ERROR` after fetch.

### A2. Soft lane — failure keywords on other levels

- [x] Also keep non-WARN/ERROR lines whose **body** matches a failure keyword regex
- [x] Minimal v1 keyword set (draft): `error`, `exception`, `timeout`, `panic`, `fatal`, `critical`
- [x] Decide whether to include softer terms (`failed`, `denied`, `warn`) — default **no** for v1 noise control
- [x] Unit tests: INFO with `timeout` kept; INFO with unrelated text dropped

**Soft LogQL (v1):** exclude hard severities, then line-grep keywords:

```logql
{service_name=~`a|b`} | detected_level!~`warn|error|fatal|critical`
  |~ `(?i)\b(error|exception|timeout|panic|fatal|critical)\b`
```

Constant: `_SOFT_FAILURE_KEYWORDS` in `loki.py`. Soft terms (`failed`, `denied`, `warn`) stay out of v1.

### A3. Combine lanes

- [ ] Prefer **one** LogQL `query_range` that ORs hard + soft lanes — **not possible** for log queries
- [x] Double-fetch hard + soft; merge by `id` (LogQL cannot OR label filter ∪ line filter)
- [x] Services still OR’d in one label matcher: `{service_label=~\`a|b|c\`}`

**Decision:** binary `or` is metrics/vectors only. v1 issues **two** `query_range` calls, merges
by line `id`, then dedupes. Shared newest-biased cap is A4.

### A4. Hard cap + direction

- [x] `limit` configurable (default `2000`)
- [x] Fetch with `direction=backward` (newest-biased when capped)
- [x] Sort results oldest→newest before returning from `fetch`
- [x] Unit/integration test: when over limit, retained lines are the newest slice of the window

**Behavior:** each lane query sends `limit` + `direction=backward`. After merge-by-id, if the
combined set is larger than `limit`, keep only `ordered[-limit:]` (newest), then dedupe and
return oldest→newest.

### A5. Map to `LogLine`

- [ ] Keep stable synthetic `id` (Loki has none)
- [ ] Map level / message / trace_id / attributes as today
- [ ] Do **not** put template clustering or token budgeting inside the adapter

### A6. Stage A acceptance

- [ ] Live or recorded Loki fixture: dual-lane query returns failure-biased lines only
- [x] Cap behavior verified (unit: newest slice under `limit`)
- [ ] Logs agent still receives `list[LogLine]` and can cite by `id`

---

## Stage B — Compress after fetch (later)

Do this **after** Stage A lands. Adapters return telemetry; clustering can live in shared logs tooling.

- [ ] Normalize message → template (strip UUIDs, numbers, IPs, timestamps)
- [ ] Group by `(service, level?, template)`
- [ ] Keep 1 exemplar + `occurrence` + first/last timestamp
- [ ] Replace or extend exact-message `dedupe_by_message` with template fingerprints
- [ ] Tests: near-duplicate lines with different request IDs collapse

---

## Stage C — Rank + LLM budget (later)

Tracked in detail in `docs/logs-llm-context-budget.md`. High-level:

- [ ] Rank groups (ERROR > WARN → higher occurrence → closer to symptom time)
- [ ] Keep top-K / pack under token budget
- [ ] Citations only for IDs actually shown to the model

---

## Implementation order (work through in order)

1. [x] Write/adjust LogQL for hard lane (structured WARN/ERROR)
2. [x] Add soft lane OR into the same query
3. [x] Switch fetch direction to backward; sort ascending after map
4. [x] Confirm `limit` default (2000) + make keyword pattern a named constant
5. [x] Unit tests for lanes + cap/direction
6. [ ] Update this checklist + short note in ADR/live-testing docs if query shape changes
7. [ ] Only then: Stage B template dedupe
8. [ ] Only then: Stage C rank/budget

---

## Explicitly out of scope for Stage A

- [ ] Fetching all INFO in the window
- [ ] Exact “miss nothing” completeness
- [ ] Elastic implementation (stub stays until Loki Stage A is solid)
- [ ] Token counting inside `LokiLogSource`
- [ ] Changing evidence `payload_hash` semantics

---

## Open questions (resolve while implementing)

- [x] Final keyword list for soft lane → `error|exception|timeout|panic|fatal|critical` (no soft terms)
- [x] Is structured level usually a **stream label**, **JSON field**, or both in our target Grafana setups?
  → **Structured metadata `detected_level`** (from JSON/logfmt/OTel at ingest). Optional stream
  label `level` exists only if the collector indexes it; v1 hard lane uses `detected_level` only.
- [ ] Should FATAL/CRITICAL be first-class levels in `LogLine` or folded into ERROR?
- [ ] Per-tenant override of `limit` / keywords via integration `config`?

---

## Success criteria (Stage A done)

- [ ] Loki fetch is dual-lane (structured severity ∪ keyword soft lane)
- [x] Volume is bounded by `limit` with intentional newest-bias under truncation
- [ ] Downstream still gets citeable `LogLine`s, oldest-first
- [ ] This file’s Stage A boxes are checked; Stage B/C remain open
