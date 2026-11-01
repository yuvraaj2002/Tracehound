-- What an investigation run produced for an incident: one row per incident, replaced on rerun.
create table investigation_results (
    incident_id uuid primary key references incidents (id) on delete cascade,
    user_id     uuid not null references auth.users (id) on delete cascade,
    run_id      uuid not null,
    scope       jsonb,
    findings    jsonb not null default '[]',
    evidence    jsonb not null default '[]',  -- list of Evidence, sorted by event_time
    hypotheses  jsonb not null default '[]',
    agent_runs  jsonb not null default '{}',  -- {agent_name: AgentRun}
    error       text,
    started_at  timestamptz,
    finished_at timestamptz,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

create index investigation_results_user_id_idx on investigation_results (user_id);

-- No policies: blocks the anon and authenticated roles on Supabase's public API.
-- The backend's owner connection bypasses RLS.
alter table investigation_results enable row level security;

alter table incidents
    add constraint incidents_state_check
    check (state in ('CREATED', 'RUNNING', 'COMPLETED', 'FAILED'));
