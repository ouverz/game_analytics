with recursive eligible_events as (
    select
        source_batch_id,
        user_id,
        session_id,
        event_name,
        event_timestamp_utc
    from {{ ref('int_events_enriched') }}
    where eligible_for_funnel
),

sessions as (
    select distinct
        source_batch_id,
        md5(cast(user_id as varchar)) as user_key,
        md5(cast(user_id as varchar) || '|' || session_id) as session_key
    from eligible_events
),

primary_steps as (
    select
        source_batch_id,
        event_name,
        primary_step_order as step_order,
        lpad(cast(primary_step_order as varchar), 2, '0')
            || ' · ' || primary_step_name as step_name,
        is_funnel_start,
        is_funnel_end
    from {{ ref('int_funnel_steps') }}
    where is_primary_step
),

event_times as (
    select
        e.source_batch_id,
        md5(cast(e.user_id as varchar)) as user_key,
        md5(cast(e.user_id as varchar) || '|' || e.session_id) as session_key,
        p.step_order,
        min(e.event_timestamp_utc) as step_at
    from eligible_events e
    inner join primary_steps p
      on e.source_batch_id = p.source_batch_id
     and e.event_name = p.event_name
    group by 1, 2, 3, 4
),

session_step_grid as (
    select
        s.source_batch_id,
        s.user_key,
        s.session_key,
        p.step_order,
        p.step_name,
        p.event_name,
        p.is_funnel_start,
        p.is_funnel_end,
        e.step_at
    from sessions s
    inner join primary_steps p using (source_batch_id)
    left join event_times e using (
        source_batch_id, user_key, session_key, step_order
    )
),

evaluated_steps as (
    select
        *,
        step_at is not null as reached_step
    from session_step_grid
    where is_funnel_start

    union all

    select
        current_step.*,
        coalesce(
            previous_step.reached_step
            and current_step.step_at >= previous_step.step_at,
            false
        ) as reached_step
    from evaluated_steps previous_step
    inner join session_step_grid current_step
      on previous_step.source_batch_id = current_step.source_batch_id
     and previous_step.user_key = current_step.user_key
     and previous_step.session_key = current_step.session_key
     and previous_step.step_order + 1 = current_step.step_order
)

select
    source_batch_id,
    user_key,
    session_key,
    step_order,
    step_name,
    event_name,
    is_funnel_start,
    is_funnel_end,
    step_at,
    reached_step,
    cast(reached_step as integer) as reached_session_count
from evaluated_steps
