with metric_grains as (
    select
        'overall' as aggregation_level,
        cast(null as varchar) as platform,
        cast(null as varchar) as client_version,
        *
    from {{ ref('fct_loading_sessions') }}

    union all

    select
        'platform_version' as aggregation_level,
        platform,
        client_version,
        *
    from {{ ref('fct_loading_sessions') }}
    where eligible_for_install_segmentation
)

select
    aggregation_level,
    platform,
    client_version,
    cast('{{ var("launch_window_start") }}' as timestamptz)::date as metric_date,
    cast(sum(started_session_count) as bigint) as started_sessions,
    cast(sum(joined_session_count) as bigint) as joined_sessions,
    sum(joined_session_count)::double
        / nullif(sum(started_session_count), 0)
        as conversion_rate,
    cast(sum(timed_session_count) as bigint) as timed_sessions,
    median(loading_time_ms) filter (where eligible_for_loading_time) / 1000.0
        as median_loading_seconds,
    quantile_cont(loading_time_ms, 0.90) filter (
        where eligible_for_loading_time
    ) / 1000.0 as p90_loading_seconds
from metric_grains
group by 1, 2, 3
