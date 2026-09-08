with raw_map as (
    select event_name, count(*) as raw_count
    from {{ ref('stg_funnel_steps') }}
    group by 1
), semantic_map as (
    select event_name, count(*) as semantic_count
    from {{ ref('funnel_event_semantics') }}
    group by 1
)
select
    coalesce(r.event_name, s.event_name) as event_name,
    coalesce(raw_count, 0) as raw_count,
    coalesce(semantic_count, 0) as semantic_count
from raw_map r
full outer join semantic_map s using (event_name)
where coalesce(raw_count, 0) != 1 or coalesce(semantic_count, 0) != 1
