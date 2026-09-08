select
    e.source_batch_id,
    md5(cast(e.user_id as varchar)) as user_key,
    md5(cast(e.user_id as varchar) || '|' || e.session_id) as session_key,
    d.branch_order,
    d.branch_name,
    min(e.event_timestamp_utc) as outcome_at
from {{ ref('int_events_enriched') }} e
inner join {{ ref('int_funnel_steps') }} d
  on e.source_batch_id = d.source_batch_id
 and e.event_name = d.event_name
where e.eligible_for_funnel
  and d.branch_order is not null
group by 1, 2, 3, 4, 5
