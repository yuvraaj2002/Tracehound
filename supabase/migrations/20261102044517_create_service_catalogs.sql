-- A user's service catalog: the Backstage catalog-info.yaml they uploaded, and the services,
-- owners and dependencies Tracehound parsed from it. One row per user, replaced whole on each
-- upload. `source` is kept so the UI can show the file back and it can be re-parsed later.
create table service_catalogs (
    user_id    uuid primary key references auth.users (id) on delete cascade,
    source     text not null check (octet_length(source) <= 1048576),
    catalog    jsonb not null check (jsonb_typeof(catalog) = 'object'),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

-- No policies: blocks the anon and authenticated roles on Supabase's public API.
-- The backend's owner connection bypasses RLS.
alter table service_catalogs enable row level security;
