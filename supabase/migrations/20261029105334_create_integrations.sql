-- Telemetry backends a user connects (Loki first). Non-secret settings (url, username,
-- service_label, org_id) live in `config`; the credential is AES-GCM encrypted by the backend
-- before insert, so the raw secret never reaches the database and is never returned by the API.
create table integrations (
    id                 uuid primary key default gen_random_uuid(),
    user_id            uuid not null references auth.users (id) on delete cascade,
    kind               text not null check (kind in ('loki')),
    config             jsonb not null default '{}'::jsonb check (jsonb_typeof(config) = 'object'),
    secret_ciphertext  bytea,
    secret_key_version smallint,
    status             text not null default 'untested'
                       check (status in ('untested', 'active', 'failing')),
    last_tested_at     timestamptz,
    last_error         text,
    created_at         timestamptz not null default now(),
    updated_at         timestamptz not null default now(),
    -- One integration per backend per user, so a run knows which one to use.
    unique (user_id, kind),
    -- A ciphertext is useless without knowing which key encrypted it.
    check ((secret_ciphertext is null) = (secret_key_version is null))
);

-- No policies: blocks the anon and authenticated roles on Supabase's public API.
-- The backend's owner connection bypasses RLS.
alter table integrations enable row level security;
