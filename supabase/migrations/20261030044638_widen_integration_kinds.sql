-- Allow the remaining specialist backends: Prometheus (Metrics), Tempo (Dependency) and
-- GitHub (Deploy). Still one row per user per kind.
alter table integrations drop constraint integrations_kind_check;
alter table integrations
    add constraint integrations_kind_check
    check (kind in ('loki', 'prometheus', 'tempo', 'github'));
