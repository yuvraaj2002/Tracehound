# Logs → LLM context budget (industry approach)

Status: **design note** — implement later. Captures how production on-call / observability copilots usually keep log volume inside an LLM context window, and how Tracehound should follow that.

Related code today:

- Filter + fetch: `src/tracehound/tools/logs/adapters/loki.py`
- Dedupe by message: `src/tracehound/tools/logs/dedupe.py`
- One-shot LLM call: `src/tracehound/agents/logs/agent.py`
- Model context metadata: `context_length` on `ModelDetails` (`src/tracehound/schemas/model_catalog.py`)
- Local ceiling: `OllamaLLM.num_ctx` (`src/tracehound/agents/inference.py`)

## What we already do

1. **Server-side narrow** — Loki query is scoped to in-scope services, an inclusive time window, and WARN/ERROR-ish lines (LogQL `|~` filter).
2. **Dedupe / cluster** — after mapping to `LogLine`, identical `message` values collapse to the first occurrence with an `occurrence` count.

These reduce load; they do **not** guarantee the serialized `LogsContext` fits the model window.

## What industry usually does (priority order)

Production systems rarely “load all matching logs, then fragment the dump.” The common stack is:

```text
filter → dedupe/cluster → rank + top-K (or tool-fetch slices) → hard token budget / truncate
                                                              ↘ map-reduce only for offline “must read everything”
```

### 1. Filter hard at the source

Keep volume out of the process: service, time range, severity. Never ship an INFO firehose into the prompt. (We started this in Loki.)

### 2. Deduplicate / cluster

Collapse identical or near-identical lines; keep a count (and sometimes first/last seen). (We do exact message hash + `occurrence`.)

### 3. Rank and keep a top‑K (default for one-shot agents)

Score lines and keep a bounded set (often tens to low hundreds), for example by:

- level (ERROR before WARN),
- `occurrence`,
- proximity to alert / symptom time,
- rarity or change-like messages (restart, config, deploy markers).

The product chooses a **deliberate** K or token budget — not “fill the entire context.”

### 4. Tool-calling / iterative fetch (common in agentic products)

Start with a small context. Let the model request another slice (“logs for checkout-api 13:50–14:00”) instead of preloading everything. Each turn stays bounded. Fits chat-style copilots; harder to keep fully deterministic citations than Tracehound’s current one-fetch → one-structured-call shape.

### 5. Summarize, then deepen

Cheap first pass (heuristics or a small model) summarizes clusters (“QueuePool timeout × 400”). A second pass expands only clusters that matter.

### 6. Hard token budget + truncate (safety net)

Always measure the **exact string** that will be sent (system + user). Compare to:

```text
budget ≈ context_length - system_prompt - output_reserve - safety_margin
```

If over: drop lowest-ranked lines (or refuse / ask for a narrower window). Almost every production stack has this cap even when ranking is good.

### 7. Map-reduce / fragment (backup, not default)

Split the corpus into chunks under budget → N LLM calls → merge findings. Useful for offline “analyze everything” jobs. Costly and slow for live incident response; prefer rank/top‑K or tool-scoped fetches first.

## Recommended Tracehound path (when we implement)

Aligned with our current deterministic logs specialist:

| Step | Action | Where |
|------|--------|--------|
| Done | Severity + service + time filter | Log adapters (e.g. Loki) |
| Done | Exact-message dedupe + `occurrence` | `tools/logs/dedupe.py` via adapters |
| Later | **Observe** — log token estimate, line count, occurrence sum per run (no truncation yet) | Around `LogsAgent` / worker |
| Later | **Rank + fit to budget** — score deduped lines; keep top‑K or pack until under budget | Agent or shared context packer (not Loki) |
| Later | Optional **map-reduce** only if product requires reading beyond top‑K | Agent orchestration |
| Later | Optional **tool-scoped refetch** if we move off pure one-shot | Bigger agent redesign |

Do **not** put token budgeting inside the integration adapters; adapters return telemetry. Fitting the LLM window is an **agent / context-packer** concern.

### Counting tokens

- Rough gate: `chars / 4` on the serialized prompt.
- Better: model-appropriate tokenizer when accuracy matters.
- Budget should respect OpenRouter `context_length` when known, and Ollama `num_ctx` for local runs.

### Ranking sketch (for later)

Prefer (in order): ERROR over WARN → higher `occurrence` → closer to `symptom_window` / alert time → keep stable ordering among ties (e.g. oldest first) so runs stay comparable.

### Citations

Whatever we keep in context must remain citeable by `id`. Truncation/ranking must not invent ids. If we fragment, each fragment is a valid context with real ids; merge must not cite ids the model never saw.

## Explicitly out of scope for the first follow-up

- Template fingerprints (normalize UUIDs/numbers in messages) — separate improvement to dedupe.
- Dropping Loki/query `limit` without a replacement budget story.
- Changing evidence `payload_hash` semantics.

## Success criteria (when implemented)

- Oversized log contexts no longer fail or silently overflow the model window.
- We can explain *why* a line was kept (rank / budget), not only that Loki returned it.
- Prompt versions bump when the shape of context packing changes (`PROMPT_VERSION` in `agents/logs/prompt.py`).
