# GitHub Deployments — fetch algorithm (pseudocode)

Status: **as implemented** — review note for the deploy telemetry path.

Related code:

- Source: `src/tracehound/tools/deploys/adapters/github.py`
- Wiring (service → repo): `src/tracehound/helpers/integration_client.py` (`live_sources`)
- Agent (fetch → LLM → cited evidence): `src/tracehound/agents/deploy/agent.py`
- Canonical record: `src/tracehound/schemas/deploys.py` (`Deploy`)

## Role in an investigation

```text
triage picks deploy task + services + [change_window_start, symptom_window_end]
    → DeployAgent.build_context
        → DeploySource.fetch(services, start, end)   # GitHubDeploySource when live
            → list[Deploy]
        → LLM sees only those Deploy records
        → citations checked against shown IDs → Evidence
```

The model does not call GitHub. Code fetches; the model only summarizes and cites.

## Inputs Tracehound needs before calling GitHub

| Input | Where it comes from |
| --- | --- |
| Auth token + API base URL | GitHub integration (`Connection`) |
| Fallback `owner/repo` | GitHub integration config `repository` |
| Per-service `owner/repo` | Service catalog annotation `github.com/project-slug` |
| `environment` | Hardcoded default `"production"` on `GitHubDeploySource` |
| Services + time window | Triage scope (`change_window_start` … `symptom_window_end`) |

Repo resolution when building live sources:

```text
FOR each service in investigation services:
    repo ← catalog.repos[service] OR integration.fallback_repository
    IF repo is set:
        repos[service] ← repo
IF repos is non-empty:
    GitHubDeploySource(client, repos)
```

Convention from the deploy pipeline (not GitHub itself): optional JSON
`payload.service`, `payload.version`, `payload.config_diff` on each Deployment.

## What the GitHub API actually filters

Endpoint: `GET /repos/{owner}/{repo}/deployments`

| Filter | Sent as GitHub query param? | Applied in Tracehound? |
| --- | --- | --- |
| `environment` | yes (`production` by default) | — |
| `per_page` / `page` | yes (100 / page) | stop when page short or past `start` |
| time window | **no** | yes, on `created_at` |
| service name | **no** | yes, via `payload.service` when present |
| branch / `ref` | supported by GitHub; **we do not send it** | — |

GitHub returns deployments newest-first (for paging). Tracehound sorts the final list oldest-first.

## Pseudocode: `GitHubDeploySource.fetch`

```text
FUNCTION fetch(services, start, end) → list[Deploy]:
    result ← []
    FOR EACH service IN sorted(services ∩ keys(repos)):
        result.extend(deploys_for_service(service, start, end))
    RETURN sort(result BY (deployed_at, id) ascending)
```

### Page until older than `start`

```text
FUNCTION list_raw(repo, start) → list[raw deployment]:
    kept ← []
    FOR page = 1 .. max_pages:                    # default max_pages = 10
        batch ← GET /repos/{repo}/deployments
                 ?environment=production
                 &per_page=100
                 &page={page}

        IF batch is not a JSON array:
            RAISE unexpected response

        reached_before_start ← false
        FOR EACH raw IN batch:                    # newest → older within the page
            IF raw.created_at < start:
                reached_before_start ← true
                BREAK                             # stop signal only; do NOT keep this row
            kept.append(raw)

        IF len(batch) < 100 OR reached_before_start:
            RETURN kept                           # every in-window row for this repo was seen

    RAISE too many pages after start              # window still not fully covered
```

Notes:

- Rows with `created_at < start` are **not** kept (no `previous_version` from the prior deploy).
- Hitting `max_pages` without crossing `start` is an error, not a silent truncate.

### Map raw rows → in-window `Deploy`s for one service

```text
FUNCTION deploys_for_service(service, start, end) → list[Deploy]:
    out ← []
    FOR EACH raw IN list_raw(repos[service], start):
        payload ← raw.payload
        IF payload is a JSON string:
            payload ← parse JSON or {}
        IF payload is not an object:
            payload ← {}

        named ← payload.service
        IF named is set AND named ≠ service:
            CONTINUE                              # monorepo: skip other services' deploys
                                                  # if payload.service is absent → keep

        deployed_at ← raw.created_at
        IF deployed_at NOT IN [start, end]:
            CONTINUE                              # listed for paging completeness, then drop

        out.append(Deploy(
            id              = "gh-" + raw.id,
            service         = service,
            version         = payload.version OR raw.ref,
            previous_version = null,              # intentionally unset today
            deployed_at     = deployed_at,
            author          = raw.creator.login OR "unknown",
            commit          = raw.sha,
            change_summary  = raw.description OR "",
            config_diff     = payload.config_diff OR {},
        ))
    RETURN out
```

### Monorepo rule (one line)

```text
IF payload.service is missing     → treat deploy as belonging to the requested service
IF payload.service == service     → keep
IF payload.service == other name  → skip
```

Catalog registration still expects one service per repository today; `payload.service` is the runtime filter when a shared repo still has mixed deployments.

## Pseudocode: deploy agent after fetch

```text
FUNCTION DeployAgent(scope, run_id):
    task ← scope.task_for(DEPLOY)
    deploys ← source.fetch(task.services, change_window_start, symptom_window_end)

    answer ← LLM(
        system = deploy specialist prompt,        # report what changed; do not name root cause
        user   = <context>{ question, services, window, deploys }</context>,
        schema = { summary, findings: [{ claim, deploy_ids }] }
    )

    IF any cited deploy_id was not in `deploys`:
        RAISE
    RETURN SpecialistReport(findings + Evidence for each unique cited deploy)
```

## Mental model

```text
                    GitHub knows                         Tracehound adds
            ┌─────────────────────────┐        ┌──────────────────────────────┐
            │ repo                    │        │ service ↔ owner/repo map     │
            │ environment=production  │   +    │ time window on created_at    │
            │ paging (newest first)   │        │ payload.service (monorepo)   │
            └─────────────────────────┘        │ payload.version / config_diff│
                                               └──────────────────────────────┘
                                                         │
                                                         ▼
                                               canonical Deploy records
                                                         │
                                                         ▼
                                               LLM cites only those IDs
```
