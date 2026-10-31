-- What each plan gives: one row per plan, edited in place. A change to credits reaches every
-- subscriber of the plan; prices live in plan_prices and are versioned instead.
create table plans (
    id           uuid primary key default gen_random_uuid(),
    -- Stable key the code checks ('free', 'pro'); display_name is free to change.
    code         text not null unique check (code ~ '^[a-z0-9_]{1,50}$'),
    display_name text not null check (length(display_name) between 1 and 100),
    -- Credits granted per month, whatever the billing interval. One credit = one investigation run.
    credits      integer not null check (credits >= 0),
    is_active    boolean not null default true,
    -- Order on the pricing page, lowest first.
    sort_order   smallint not null default 0,
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now()
);

-- What a plan costs: one row per plan, currency and billing interval. A price row is never
-- repriced in place: to change a price, set is_active = false on the old row and insert a new
-- one, so subscriptions keep pointing at the terms they bought. price_minor is an integer in
-- the currency's minor unit (cents, paise), so $19.99 is 1999.
create table plan_prices (
    id               uuid primary key default gen_random_uuid(),
    -- Restrict: a plan with prices (and so, later, subscriptions) is retired, not deleted.
    plan_id          uuid not null references plans (id) on delete restrict,
    currency         char(3) not null check (currency ~ '^[A-Z]{3}$'),
    price_minor      integer not null check (price_minor >= 0),
    billing_interval text not null check (billing_interval in ('month', 'year')),
    is_active        boolean not null default true,
    created_at       timestamptz not null default now(),
    updated_at       timestamptz not null default now()
);

create index plan_prices_plan_id_idx on plan_prices (plan_id);

-- At most one live price per plan, currency and interval; retired rows don't count.
create unique index plan_prices_active_key
    on plan_prices (plan_id, currency, billing_interval)
    where is_active;

-- No policies: blocks the anon and authenticated roles on Supabase's public API.
-- The backend's owner connection bypasses RLS.
alter table plans enable row level security;
alter table plan_prices enable row level security;
