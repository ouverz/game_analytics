with ordered_steps as (
    select
        step_order,
        sessions,
        lag(sessions) over (order by step_order) as previous_sessions
    from {{ ref('mart_primary_funnel') }}
)

select step_order, sessions, previous_sessions
from ordered_steps
where sessions > previous_sessions
