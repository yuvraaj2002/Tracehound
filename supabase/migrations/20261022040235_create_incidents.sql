-- Incident intake records. The API is the only writer; it connects as the database owner.
create table incidents (
    id           uuid primary key,
    run_id       uuid not null,
    service_id   text not null,
    symptom      text not null,
    severity     text not null check (severity in ('low', 'medium', 'high', 'critical')),
    window_start timestamptz not null,
    window_end   timestamptz not null check (window_end > window_start),
    trace_id     text,
    state        text not null default 'CREATED',
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now()
);

create index incidents_created_at_idx on incidents (created_at desc);

-- No policies: blocks the anon and authenticated roles on Supabase's public API.
-- The backend's owner connection bypasses RLS.
alter table incidents enable row level security;
