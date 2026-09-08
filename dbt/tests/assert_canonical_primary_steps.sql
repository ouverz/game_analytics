select
    source_batch_id,
    count(*) filter (where is_primary_step) as primary_steps,
    count(distinct primary_step_order) filter (
        where is_primary_step
    ) as distinct_step_orders,
    min(primary_step_order) filter (where is_primary_step) as first_step,
    max(primary_step_order) filter (where is_primary_step) as last_step
from {{ ref('int_funnel_steps') }}
group by 1
having primary_steps != 10
    or distinct_step_orders != 10
    or first_step != 1
    or last_step != 10
