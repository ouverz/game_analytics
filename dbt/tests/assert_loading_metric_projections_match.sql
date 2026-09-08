with performance as (
    select *
    from {{ ref('mart_loading_performance') }}
),
funnel_boundaries as (
    select
        max(sessions) filter (where step_order = 1) as started_sessions,
        max(sessions) filter (where step_order = 10) as joined_sessions
    from {{ ref('mart_primary_funnel') }}
),
expected_segments as (
    select
        platform,
        client_version,
        started_sessions,
        joined_sessions,
        conversion_rate,
        median_loading_seconds,
        p90_loading_seconds
    from performance
    where aggregation_level = 'platform_version'
),
segment_differences as (
    (select * from expected_segments except select * from {{ ref('mart_segment_performance') }})
    union all
    (select * from {{ ref('mart_segment_performance') }} except select * from expected_segments)
),
overall_differences as (
    select 1 as issue
    from performance p
    cross join funnel_boundaries f
    inner join {{ ref('mart_launch_summary') }} s on true
    where p.aggregation_level = 'overall'
      and (
          p.started_sessions != f.started_sessions
          or p.joined_sessions != f.joined_sessions
          or p.started_sessions != s.started_sessions
          or p.joined_sessions != s.joined_sessions
          or p.conversion_rate != s.conversion_rate
          or p.timed_sessions != s.timed_sessions
          or p.median_loading_seconds != s.median_loading_seconds
          or p.p90_loading_seconds != s.p90_loading_seconds
      )
)
select 'segment_projection' as issue from segment_differences
union all
select 'overall_projection' from overall_differences
