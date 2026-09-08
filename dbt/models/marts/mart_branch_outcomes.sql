select
    d.branch_order,
    d.branch_name as branch_outcome,
    count(o.session_key) as observed_sessions,
    count(o.session_key) filter (
        where s.game_joined_at > o.outcome_at
    ) as continued_sessions,
    count(o.session_key) filter (
        where s.game_joined_at > o.outcome_at
    )::double / nullif(count(o.session_key), 0) as continuation_rate
from (
    select distinct branch_order, branch_name
    from {{ ref('dim_funnel_steps') }}
    where branch_order is not null
) d
left join {{ ref('fct_loading_branch_events') }} o using (branch_order, branch_name)
left join {{ ref('fct_loading_sessions') }} s using (
    source_batch_id, user_key, session_key
)
group by 1, 2
