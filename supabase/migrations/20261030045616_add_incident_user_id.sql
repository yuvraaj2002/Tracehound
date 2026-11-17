-- Scope incidents to the user who created them. Existing rows have no owner, so the
-- column is added NOT NULL without a backfill (the table was empty when this ran).
alter table incidents
    add column user_id uuid not null references auth.users (id) on delete cascade;

-- Incidents are always listed per user, newest first; this replaces the created_at-only index.
drop index incidents_created_at_idx;
create index incidents_user_id_idx on incidents (user_id, created_at desc);
