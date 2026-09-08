select
    started_sessions,
    joined_sessions,
    conversion_rate,
    timed_sessions,
    median_loading_seconds,
    p90_loading_seconds
from {{ ref('mart_loading_performance') }}
where aggregation_level = 'overall'
