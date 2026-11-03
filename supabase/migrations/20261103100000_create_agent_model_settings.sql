-- Which model each investigation agent runs on, per user. One row per user; `config` holds
-- {"agents": {"<agent id>": {"provider", "model"}}}. An agent with no entry uses the
-- default in the backend's models config, so rows only ever hold what the user changed.
-- The backend validates agent ids and models before writing; the database only guards the shape.
create table agent_model_settings (
    id         uuid primary key default gen_random_uuid(),
    user_id    uuid not null unique references auth.users (id) on delete cascade,
    config     jsonb not null default '{}'::jsonb check (jsonb_typeof(config) = 'object'),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

-- No policies: blocks the anon and authenticated roles on Supabase's public API.
-- The backend's owner connection bypasses RLS.
alter table agent_model_settings enable row level security;
