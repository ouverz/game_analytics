-- Aggregate-only cross-check for the FTUE KPI output.
-- Run after the documented build:
-- duckdb data/superset_analytics.duckdb < sql/reconcile_ftue_kpis.sql

with installs as (
    select user_id, install_date
    from analytics.stg_installs
    qualify row_number() over (partition by user_id order by source_line) = 1
),

session_events as (
    select
        user_id,
        session_id,
        min(event_timestamp_utc) filter (
            where event_name = 'INIT_CLIENT_START'
        ) as client_start_at,
        min(event_timestamp_utc) filter (
            where event_name = 'INIT_CONFIG_LOADED'
        ) as config_loaded_at,
        min(event_timestamp_utc) filter (
            where event_name = 'INIT_LOCALIZATION_END'
        ) as localization_ended_at,
        min(event_timestamp_utc) filter (
            where event_name = 'INIT_UPDATE_MAINTENANCE_CHECK'
        ) as maintenance_checked_at,
        min(event_timestamp_utc) filter (
            where event_name = 'INIT_DATA_MODEL_LOAD_START'
        ) as data_load_started_at,
        min(event_timestamp_utc) filter (
            where event_name = 'INIT_DATA_MODEL_LOAD_END'
        ) as data_load_ended_at,
        min(event_timestamp_utc) filter (
            where event_name = 'INIT_READY_TO_START'
        ) as ready_to_start_at,
        min(event_timestamp_utc) filter (
            where event_name = 'INIT_PLAYER_LOGIN_START'
        ) as login_started_at,
        min(event_timestamp_utc) filter (
            where event_name = 'INIT_PLAYER_LOGIN_END'
        ) as login_ended_at,
        min(event_timestamp_utc) filter (
            where event_name = 'INIT_GAME_JOINED'
        ) as game_joined_at
    from analytics.int_events_enriched
    where eligible_for_funnel
    group by 1, 2
),

sequential_sessions as (
    select
        *,
        client_start_at is not null
        and config_loaded_at >= client_start_at
        and localization_ended_at >= config_loaded_at
        and maintenance_checked_at >= localization_ended_at
        and data_load_started_at >= maintenance_checked_at
        and data_load_ended_at >= data_load_started_at
        and ready_to_start_at >= data_load_ended_at
        and login_started_at >= ready_to_start_at
        and login_ended_at >= login_started_at
        and game_joined_at >= login_ended_at as reached_game_joined
    from session_events
),

first_sessions as (
    select s.*
    from sequential_sessions s
    inner join installs i using (user_id)
    where s.client_start_at is not null
    qualify row_number() over (
        partition by s.user_id order by s.client_start_at, s.session_id
    ) = 1
),

first_battles as (
    select
        f.user_id,
        min(e.event_timestamp_utc) as first_battle_at
    from first_sessions f
    inner join analytics.int_events_enriched e
      on f.user_id = e.user_id
     and f.session_id = e.session_id
     and e.eligible_for_funnel
     and e.event_name = 'BATTLE_STARTED'
     and e.event_timestamp_utc >= f.game_joined_at
    where f.reached_game_joined
    group by 1
),

d1_mature_installs as (
    select *
    from installs
    where install_date + interval 1 day < date '2026-06-23'
),

d1_returned as (
    select distinct i.user_id
    from d1_mature_installs i
    inner join analytics.int_events_enriched e
      on i.user_id = e.user_id
     and e.eligible_for_funnel
     and e.event_name = 'INIT_CLIENT_START'
     and cast(e.event_timestamp_utc at time zone 'UTC' as date)
         = i.install_date + interval 1 day
)

select
    (select count(*) from first_sessions) as eligible_new_players,
    (select count(*) from first_sessions where reached_game_joined)
        as first_session_game_entries,
    (select count(*) from first_battles) as first_session_activations,
    (
        select median(date_diff(
            'millisecond', f.client_start_at, b.first_battle_at
        )) / 1000.0
        from first_sessions f
        inner join first_battles b using (user_id)
    ) as median_time_to_first_battle_seconds,
    (
        select quantile_cont(date_diff(
            'millisecond', f.client_start_at, b.first_battle_at
        ), 0.90) / 1000.0
        from first_sessions f
        inner join first_battles b using (user_id)
    ) as p90_time_to_first_battle_seconds,
    (select count(*) from d1_mature_installs) as d1_mature_installs,
    (select count(*) from d1_returned) as d1_returned_players;
