with session_metadata as (
    select
        source_batch_id,
        md5(cast(user_id as varchar)) as user_key,
        md5(cast(user_id as varchar) || '|' || session_id) as session_key,
        arg_min(platform, event_timestamp_utc) as platform,
        arg_min(client_version, event_timestamp_utc) as client_version,
        arg_min(install_source, event_timestamp_utc) as install_source,
        arg_min(country, event_timestamp_utc) as country,
        arg_min(is_first_session, event_timestamp_utc) as is_first_session,
        bool_and(eligible_for_install_segmentation)
            as eligible_for_install_segmentation,
        bool_or(session_has_time_reversal) as session_has_time_reversal
    from {{ ref('int_events_enriched') }}
    where eligible_for_funnel
    group by 1, 2, 3
),

session_boundaries as (
    select
        source_batch_id,
        user_key,
        session_key,
        max(step_at) filter (where is_funnel_start) as client_start_at,
        max(step_at) filter (where is_funnel_end) as game_joined_at,
        bool_or(reached_step) filter (where is_funnel_start)
            as reached_client_start,
        bool_or(reached_step) filter (where is_funnel_end)
            as reached_game_joined
    from {{ ref('int_loading_session_steps') }}
    group by 1, 2, 3
)

select
    m.*,
    b.client_start_at,
    b.game_joined_at,
    b.reached_client_start,
    b.reached_game_joined,
    cast(b.reached_client_start as integer) as started_session_count,
    cast(b.reached_game_joined as integer) as joined_session_count,
    b.reached_game_joined
        and not m.session_has_time_reversal
        and b.game_joined_at >= b.client_start_at as eligible_for_loading_time,
    case
        when b.reached_game_joined
         and not m.session_has_time_reversal
         and b.game_joined_at >= b.client_start_at
        then date_diff('millisecond', b.client_start_at, b.game_joined_at)
    end as loading_time_ms,
    cast(
        b.reached_game_joined
        and not m.session_has_time_reversal
        and b.game_joined_at >= b.client_start_at
        as integer
    ) as timed_session_count
from session_metadata m
inner join session_boundaries b using (source_batch_id, user_key, session_key)
