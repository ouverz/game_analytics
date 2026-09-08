select
    source_batch_id,
    md5(source_batch_id || '|' || cast(source_line as varchar)) as battle_key,
    md5(cast(user_id as varchar)) as user_key,
    md5(cast(user_id as varchar) || '|' || session_id) as session_key,
    event_timestamp_utc as battle_started_at
from {{ ref('int_events_enriched') }}
where eligible_for_funnel
  and event_name = 'BATTLE_STARTED'
