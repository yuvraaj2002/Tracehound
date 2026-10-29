-- API keys issued to signed-in users. Only the SHA-256 hash of the raw key is stored;
-- prefix and suffix are kept so the UI can show a recognisable masked key.
create table api_keys (
    id           uuid primary key default gen_random_uuid(),
    user_id      uuid not null references auth.users (id) on delete cascade,
    name         text not null check (length(name) between 1 and 100),
    hash         text not null unique,
    prefix       text not null,
    suffix       text not null,
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now(),
    last_used_at timestamptz,
    revoked_at   timestamptz
);

create index api_keys_user_id_idx on api_keys (user_id, created_at desc);

-- No policies: blocks the anon and authenticated roles on Supabase's public API.
-- The backend's owner connection bypasses RLS.
alter table api_keys enable row level security;
