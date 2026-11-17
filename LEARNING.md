# Learning notes

Concepts that came up while building Tracehound, written down so the reasoning isn't lost.
Each entry says what the idea is, why we use it, and where it shows up in the code.

## Contents

- [Storing money in minor units](#storing-money-in-minor-units)
- [Supabase access and refresh tokens](#supabase-access-and-refresh-tokens)
- [Supporting many LLM providers (BYOK)](#supporting-many-llm-providers-byok)
- [The LGTM stack and the otel-lgtm image](#the-lgtm-stack-and-the-otel-lgtm-image)
- [The OpenTelemetry Collector](#the-opentelemetry-collector)
- [Database connection pool exhaustion](#database-connection-pool-exhaustion)
- [ORM models vs. migrations](#orm-models-vs-migrations)

---

## Storing money in minor units

*Came up in: `supabase/migrations/20261030130318_create_plans.sql` (`plan_prices.price_minor`)*

`price_minor` stores a price as a whole number in the currency's minor unit, its smallest
unit: cents for US dollars, paise for rupees. So $19.99 is stored as `1999`, and ₹499 as
`49900`.

We do this because computers store numbers in binary. Every whole number has an exact
binary form, but most decimal fractions don't. Just as 1/3 can't be written exactly in
decimal (0.333… forever), 1/10 can't be written exactly in binary. So a float price like
19.99 is really stored as a value slightly off from 19.99:

```python
>>> 0.1 + 0.2
0.30000000000000004
```

Each time we add tax, multiply by a quantity or apply a coupon, those tiny errors can build
up, and the total can end up off by a cent or more. Integers don't have this problem:
`1999 + 1999` is always exactly `3998`. When a calculation produces a fraction of a cent,
like a 20% discount, we round it once, on purpose, in one place. We only convert back to
"$19.99" when showing the price to a user.

**Beyond the database.** JavaScript has one number type (a float), so a JSON price of
`19.99` becomes a float in the React UI whatever the server used, while `1999` arrives
unchanged. Stripe (`unit_amount`) and Razorpay (`amount`) also use minor units, so a
payment integration can pass the value straight through.

**Edge cases.**
- Not every currency has 2 decimal places: JPY has 0 (¥500 is `500`), KWD has 3. Use
  `Intl.NumberFormat` (JS) or a currency-aware formatter instead of always dividing by 100.
- Postgres `numeric(10,2)` would also be exact inside the database. Minor units mainly
  help once the value leaves the database: in JSON, JavaScript and payment APIs.
- The column is named `price_minor`, not `price`, so nobody reads `1900` as $1,900.

---

## Supabase access and refresh tokens

*Came up in: the UI staying signed in the next morning and calling `GET /v1/me`*

A Supabase session has two tokens, both stored in the browser's localStorage by supabase-js:

- **Access token (JWT):** valid for 1 hour by default (dashboard: Authentication → Sessions →
  JWT expiry limit). This is the only token with a short expiry.
- **Refresh token:** no timer by default. It can be used once, and using it issues a new
  access token and a new refresh token.

So being signed in the next day is expected. On page load, supabase-js sees the stored
access token has expired and exchanges the refresh token for a new pair
(`/auth/v1/token?grant_type=refresh_token`). It also refreshes in the background while a
tab stays open. The user stays signed in until they sign out, clear site storage, or hit an
optional time-box or inactivity limit set in the dashboard.

**In our stack.** The refresh happens inside supabase-js in the React (Vite) app. FastAPI
never sees the refresh token. It only receives the fresh access token in the
`Authorization` header (e.g. on `/v1/me`) and validates that JWT.

---

## Supporting many LLM providers (BYOK)

*Came up in: asking how to let users bring their own API key for models other than Ollama*

Every provider has its own SDK and request format, so the usual answer is to hide them
behind one internal interface (the adapter pattern). The agents call `generate()` and never
import a vendor SDK directly. There are three common ways to fill that interface:

1. **One adapter class per provider.** You write `AnthropicLLM`, `OpenAILLM`, `OllamaLLM`,
   and so on. This gives full control but is the most code to maintain. LangChain and the
   Vercel AI SDK are built this way.
2. **A gateway library such as LiteLLM.** One `completion(model="anthropic/claude-...")` call
   translates to 100+ providers, including key handling, retries and cost tracking. This is
   the most common shortcut.
3. **OpenAI-compatible endpoints.** Ollama, vLLM, Groq, Together, OpenRouter and Gemini all
   accept the OpenAI chat format. One OpenAI client plus a different `base_url` and key
   covers them, though Anthropic's native API is still separate.

The hard part is usually structured output, not the chat call itself. Providers get JSON in
different ways: a JSON schema field, tool calling, or plain JSON mode. Libraries such as
Instructor, or LiteLLM's `response_format`, smooth this over. Small models still need
validation and retries.

**What BYOK adds on top:**

- **Store keys encrypted and per user.** Use something like Supabase Vault or envelope
  encryption. A key is decrypted only in the worker at call time, never sent back to the
  browser (show only the last 4 characters), and never logged.
- **Check the key when it is saved** with a cheap call, such as listing models.
- **Save the provider and model on each run**, so results can be compared and reproduced.
- **Have a fallback**, such as the local Ollama model, when no key is set.

**In our stack.** The seam already exists: `StructuredLLM` (a Protocol) in
`src/tracehound/agents/inference.py`, with `OllamaLLM` as its only implementation. The worker
picks the model in `src/tracehound/worker/runner.py`. BYOK means adding implementations (or
one LiteLLM-backed one) and choosing among them per user instead of from `OLLAMA_MODEL`.

---

## The LGTM stack and the otel-lgtm image

*Came up in: planning live integration tests (`docs/live-integration-testing.md`)*

LGTM is Grafana Labs' name for its open-source observability stack:

- **L**oki stores logs.
- **G**rafana is the UI for dashboards and queries.
- **T**empo stores traces.
- **M**imir stores metrics. It is a scalable, Prometheus-compatible store, queried with PromQL.

`grafana/otel-lgtm` is a single Docker image that runs a small version of this stack for
development, plus an OpenTelemetry Collector in front. An app sends all its telemetry to one
OTLP endpoint (port 4317 or 4318), and the collector sends logs to Loki, traces to Tempo and
metrics to the metrics store. In this image the metrics store is plain Prometheus, the lighter
option for local use.

It is meant for demos and testing only: one container, no high availability, and data kept only
as long as the container runs.

**In our stack.** It stands in for a customer's real backends, so Tracehound's Loki, Tempo and
Prometheus adapters can be tested against real data on `localhost`.

---

## The OpenTelemetry Collector

*Came up in: planning live integration tests with the `grafana/otel-lgtm` image*

OpenTelemetry (OTel) is a vendor-neutral standard for producing telemetry (logs, metrics and
traces), with SDKs for most languages and one wire protocol, OTLP. The **Collector** is a
separate program that sits between apps and storage backends and forwards telemetry.

It is a pipeline built from three kinds of parts, set up in a YAML config:

- **Receivers** take data in, e.g. OTLP on ports 4317 (gRPC) and 4318 (HTTP), or by scraping
  Prometheus endpoints.
- **Processors** change data on the way through: batching, adding labels such as
  `deployment.environment`, dropping noisy data, sampling traces, removing secrets.
- **Exporters** send data out, e.g. logs to Loki, traces to Tempo, metrics to Prometheus.
  The same data can go to more than one backend.

**Why not send straight to each backend?** Apps then only know one address and one protocol.
Switching vendors, or sending to two at once, becomes a Collector config change, not a code
change in every service. The Collector also buffers and retries if a backend is down.

**In our stack.** Tracehound never talks to the Collector. It only reads from Loki, Tempo and
Prometheus. The Collector matters for the test setup: the demo checkout app sends everything to
it, and it fills the three backends that Tracehound then queries.

---

## Database connection pool exhaustion

*Came up in: the dummy `checkout-api` in `simulation/checkout_api/app.py`*

Opening a database connection is slow, so apps keep a **pool** of open connections and lend
them out: a request borrows one, runs its queries and gives it back. The pool has a maximum size
and a timeout for how long a request will wait for a free connection.

How many connections are busy at once is roughly *requests per second × seconds each request
holds a connection* (Little's law). At 40 req/s × 0.2s, about 8 are busy on average.

- A pool of 20 handles up to 20 / 0.2 = 100 req/s, so 40 req/s is easy.
- A pool of 5 handles only 5 / 0.2 = 25 req/s. At 40 req/s, about 15 more requests arrive each
  second than can be served, so the queue keeps growing. Once a request has waited longer than
  the timeout (2s) it gives up, and the app returns 503.

The traffic must be **open loop** (sent on a fixed schedule, like real users) for this to show.
If each client waits for its answer before sending the next request, a slow server just slows
the clients down, and the queue never builds.

What it looks like: the database itself is fine (low CPU, few connections), the app's request
rate is steady, but errors and latency jump right after the pool shrinks. This pattern is how
Tracehound should tell it apart from "the database is overloaded" or "traffic spiked".

---

## ORM models vs. migrations

*Came up in: `src/tracehound/models/`, `supabase/migrations/`, ADR 0007*

An ORM (SQLAlchemy here) maps each table to a Python class, so a query reads as
`select(Incident).where(Incident.user_id == user_id)` and not as a SQL string. The column
names are then checked by Python: a typo in an attribute fails at import time or in the
type checker, not at query time.

Two separate things describe a table, though:

- **Migrations** (`supabase/migrations/*.sql`) *change* the real database. They run once,
  in order, and Supabase records which ones have run.
- **Models** (`tracehound/models/*.py`) *describe* the database to Python. They never
  change it.

Many projects generate migrations from the models (Alembic's autogenerate). We go the other
way: migrations come first because Supabase owns them and they hold things models describe
poorly (row level security, references to Supabase's `auth.users`). The cost is that the two
can drift, so `test_models_match_migrations.py` builds the migrations into a scratch schema
and compares each model's columns, nullability and primary key with what was built.

Example: adding a `last_used_ip` column to `api_keys` means a new migration file
(`alter table api_keys add column last_used_ip inet;`) *and* a line
`last_used_ip: Mapped[str | None] = mapped_column(INET)` in `models/api_key.py`.

