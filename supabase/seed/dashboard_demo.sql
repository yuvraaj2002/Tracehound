-- Demo incidents for the dashboard, owned by one user (looked up by email).
-- Needs migration 20261030045616_add_incident_user_id.sql applied first.
-- Every demo row's id starts with `de3000`, so they can be removed with:
--   delete from incidents where id::text like 'de3000%';
-- Re-running replaces the previous demo rows.

delete from incidents where id::text like 'de3000%';

select setseed(0.42);

with owner as (
    select id from auth.users where email = 'ys7233831@gmail.com'
),
services(service_id, weight) as (
    values ('checkout-api', 5), ('payments', 4), ('auth-service', 3), ('search', 2),
           ('inventory', 2), ('notifications', 1), ('gateway', 1)
),
symptoms(severity, symptom) as (
    values
        ('critical', 'Error rate above 25% on all endpoints after deploy'),
        ('critical', 'Database connection pool exhausted, requests timing out'),
        ('high', 'p95 latency jumped from 200ms to 3s'),
        ('high', '5xx responses spiking on POST /orders'),
        ('high', 'Upstream dependency returning 503 intermittently'),
        ('medium', 'Elevated retry rate on the message queue consumer'),
        ('medium', 'Memory usage climbing steadily, GC pauses above 500ms'),
        ('medium', 'Cache hit ratio dropped from 92% to 60%'),
        ('low', 'Slow query warnings on the reporting replica'),
        ('low', 'Occasional 429s from the rate limiter'),
        ('low', 'Disk usage above 80% on one node')
),
-- More incidents in recent weeks, so the 7- and 30-day views have shape.
picks as (
    select n,
           now() - (power(random(), 1.6) * interval '89 days') - random() * interval '1 hour' as created_at,
           random() as r_severity, random() as r_service, random() as r_symptom,
           random() as r_window, random() as r_trace
    from generate_series(1, 140) as n
),
severity_pick as (
    select p.*,
           case when r_severity < .08 then 'critical' when r_severity < .30 then 'high'
                when r_severity < .62 then 'medium' else 'low' end as severity
    from picks p
),
service_weights as (
    select service_id,
           sum(weight) over (order by service_id) :: float / sum(weight) over () as upper_bound
    from services
)
insert into incidents (id, run_id, user_id, service_id, symptom, severity, window_start,
                       window_end, trace_id, state, created_at, updated_at)
select overlay(gen_random_uuid()::text placing 'de3000' from 1 for 6)::uuid,
       gen_random_uuid(),
       (select id from owner),
       (select service_id from service_weights where upper_bound >= s.r_service
        order by upper_bound limit 1),
       (select symptom from symptoms where symptoms.severity = s.severity
        order by md5(symptom || s.n) limit 1),
       s.severity,
       s.created_at - (5 + s.r_window * 115) * interval '1 minute' - interval '2 minutes',
       s.created_at - interval '2 minutes',
       case when s.r_trace < .7 then substr(md5(s.n::text), 1, 16) end,
       'CREATED',
       s.created_at,
       s.created_at
from severity_pick s
where exists (select 1 from owner);

select count(*) as demo_incidents from incidents where id::text like 'de3000%';
