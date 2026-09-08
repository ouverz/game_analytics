with step_counts as (
    select
        step_order,
        step_name,
        cast(sum(reached_session_count) as bigint) as sessions,
        count(distinct user_key) filter (where reached_step) as users
    from {{ ref('fct_loading_session_steps') }}
    group by 1, 2
),

with_rates as (
    select
        *,
        lag(sessions, 1, sessions) over (order by step_order)
            as previous_sessions,
        first_value(sessions) over (order by step_order)
            as starting_sessions
    from step_counts
)

select
    step_order,
    step_name,
    cast('{{ var("launch_window_start") }}' as timestamptz)::date as metric_date,
    sessions,
    users,
    previous_sessions - sessions as drop_off_sessions,
    sessions::double / nullif(previous_sessions, 0) as step_conversion_rate,
    sessions::double / nullif(starting_sessions, 0) as start_conversion_rate
from with_rates
