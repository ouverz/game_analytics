select
    platform,
    client_version,
    started_sessions,
    joined_sessions,
    conversion_rate,
    median_loading_seconds,
    p90_loading_seconds
from {{ ref('mart_loading_performance') }}
where aggregation_level = 'platform_version'
