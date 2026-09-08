with first_sessions as (
    select f.*
    from {{ ref('fct_loading_sessions') }} f
    inner join {{ ref('dim_installs') }} i using (source_batch_id, user_key)
    where f.reached_client_start
    qualify row_number() over (
        partition by f.source_batch_id, f.user_key
        order by f.client_start_at, f.session_key
    ) = 1
),

first_battles as (
    select
        f.source_batch_id,
        f.user_key,
        min(b.battle_started_at) as first_battle_at
    from first_sessions f
    inner join {{ ref('fct_battle_starts') }} b using (
        source_batch_id, user_key, session_key
    )
    where f.reached_game_joined
      and b.battle_started_at >= f.game_joined_at
    group by 1, 2
),

activation_durations as (
    select
        date_diff('millisecond', f.client_start_at, b.first_battle_at)
            as time_to_first_battle_ms
    from first_sessions f
    inner join first_battles b using (source_batch_id, user_key)
),

d1_mature_installs as (
    select
        i.source_batch_id,
        i.user_key,
        i.install_date,
        i.platform,
        coalesce(f.client_version, 'Unknown') as client_version
    from {{ ref('dim_installs') }} i
    left join first_sessions f using (source_batch_id, user_key)
    where i.install_date + interval 1 day
        < cast(
            cast('{{ var("launch_window_end") }}' as timestamptz)
            at time zone 'UTC'
            as date
        )
),

d1_population as (
    select
        i.*,
        exists (
            select 1
            from {{ ref('fct_loading_sessions') }} f
            where f.source_batch_id = i.source_batch_id
              and f.user_key = i.user_key
              and f.reached_client_start
              and cast(f.client_start_at at time zone 'UTC' as date)
                = i.install_date + interval 1 day
        ) as returned_on_d1
    from d1_mature_installs i
),

retention_metrics as (
    select
        'overall' as aggregation_level,
        cast(null as varchar) as platform,
        cast(null as varchar) as client_version,
        count(*) as d1_mature_installs,
        count(*) filter (where returned_on_d1) as d1_returned_players
    from d1_population

    union all

    select
        'platform_version' as aggregation_level,
        platform,
        client_version,
        count(*) as d1_mature_installs,
        count(*) filter (where returned_on_d1) as d1_returned_players
    from d1_population
    group by platform, client_version
),

counts as (
    select
        count(*) as eligible_new_players,
        count(*) filter (where reached_game_joined) as first_session_game_entries
    from first_sessions
),

activation_counts as (
    select count(*) as first_session_activations
    from first_battles
),

activation_stats as (
    select
        median(time_to_first_battle_ms) / 60000.0
            as median_time_to_first_battle_minutes,
        quantile_cont(time_to_first_battle_ms, 0.90) / 60000.0
            as p90_time_to_first_battle_minutes,
        count(time_to_first_battle_ms) as activation_timing_sample_size
    from activation_durations
),

overall_ftue as (
    select
        r.aggregation_level,
        r.platform,
        r.client_version,
        c.eligible_new_players,
        c.first_session_game_entries,
        c.first_session_game_entries::double
            / nullif(c.eligible_new_players, 0) as first_session_game_entry_rate,
        a.first_session_activations,
        a.first_session_activations::double
            / nullif(c.eligible_new_players, 0) as first_session_activation_rate,
        a.first_session_activations::double
            / nullif(c.first_session_game_entries, 0)
            as activation_rate_among_game_entries,
        s.median_time_to_first_battle_minutes,
        s.p90_time_to_first_battle_minutes,
        s.activation_timing_sample_size,
        r.d1_mature_installs,
        r.d1_returned_players,
        r.d1_returned_players::double
            / nullif(r.d1_mature_installs, 0) as d1_retention_rate
    from retention_metrics r
    cross join counts c
    cross join activation_counts a
    cross join activation_stats s
    where r.aggregation_level = 'overall'
),

segment_retention as (
    select
        aggregation_level,
        platform,
        client_version,
        cast(null as bigint) as eligible_new_players,
        cast(null as bigint) as first_session_game_entries,
        cast(null as double) as first_session_game_entry_rate,
        cast(null as bigint) as first_session_activations,
        cast(null as double) as first_session_activation_rate,
        cast(null as double) as activation_rate_among_game_entries,
        cast(null as double) as median_time_to_first_battle_minutes,
        cast(null as double) as p90_time_to_first_battle_minutes,
        cast(null as bigint) as activation_timing_sample_size,
        d1_mature_installs,
        d1_returned_players,
        d1_returned_players::double
            / nullif(d1_mature_installs, 0) as d1_retention_rate
    from retention_metrics
    where aggregation_level = 'platform_version'
)

select * from overall_ftue
union all by name
select * from segment_retention
