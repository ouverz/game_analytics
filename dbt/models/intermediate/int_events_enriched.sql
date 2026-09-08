with enriched as (
    select
        e.*,
        i.user_id is not null as has_matching_install,
        i.install_date,
        i.platform as install_platform,
        i.install_source,
        i.country,
        e.platform is not null and i.platform is not null and e.platform != i.platform
            as has_platform_conflict,
        i.install_date is not null
            and cast(e.event_timestamp_utc at time zone 'UTC' as date) < i.install_date
            as is_pre_install_event,
        m.logical_step_key,
        m.funnel_section,
        m.event_role,
        m.outcome_value,
        m.applicability,
        m.funnel_scope,
        m.primary_step_order,
        m.primary_step_name,
        m.branch_order,
        m.branch_name,
        coalesce(m.is_primary_endpoint, false) as is_primary_endpoint,
        coalesce(m.is_explicit_failure, false) as is_explicit_failure,
        case
            when regexp_full_match(e.session_id, '.*[0-9]+$')
            then try_cast(regexp_extract(e.session_id, '([0-9]+)$', 1) as bigint)
        end as session_id_count,
        m.event_name is not null as is_configured_funnel_event
    from {{ ref('stg_events') }} e
    left join {{ ref('int_installs') }} i
      on e.source_batch_id = i.source_batch_id
     and e.user_id = i.user_id
    left join {{ ref('int_funnel_steps') }} m
      on e.source_batch_id = m.source_batch_id
     and e.event_name = m.event_name
),

sequenced as (
    select
        *,
        event_timestamp_utc < lag(event_timestamp_utc) over (
            partition by source_batch_id, user_id, session_id order by source_line
        ) as row_has_time_reversal
    from enriched
),

session_classified as (
    select
        *,
        coalesce(bool_or(row_has_time_reversal) over (
            partition by source_batch_id, user_id, session_id
        ), false) as session_has_time_reversal
    from sequenced
)

select
    *,
    eligible_for_funnel_base as eligible_for_funnel,
    eligible_for_funnel_base
        and has_matching_install
        and not has_platform_conflict
        as eligible_for_install_segmentation,
    eligible_for_funnel_base and not session_has_time_reversal as eligible_for_timing,
    session_id_count is not null
        and session_count is not null
        and session_id_count != session_count as has_session_count_conflict,
    session_count is not null
        and is_first_session is not null
        and ((session_count = 1 and not is_first_session)
          or (session_count != 1 and is_first_session)) as has_first_session_conflict,
    applicability = 'ios' and platform != 'iOS' as is_platform_inapplicable
from session_classified
