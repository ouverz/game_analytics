with source as (
    select e.*
    from {{ source('raw', 'events') }} e
    inner join {{ source('meta', 'source_batches') }} b using (source_batch_id)
    where b.promotion_status = 'promoted'
),

extracted as (
    select
        source_batch_id,
        source_line,
        ingested_at,
        raw_line_hash,
        payload as raw_payload,
        json_exists(payload, '$.event_name') as event_name_is_present,
        json_exists(payload, '$.user_id') as user_id_is_present,
        json_exists(payload, '$.session_id') as session_id_is_present,
        json_exists(payload, '$.timestamp') as timestamp_is_present,
        json_exists(payload, '$.network_type') as network_type_is_present,
        json_exists(payload, '$.event_properties') as event_properties_is_present,
        json_type(payload, '$.user_id') as raw_user_id_json_type,
        json_type(payload, '$.session_count') as raw_session_count_json_type,
        json_type(payload, '$.is_first_session') as raw_is_first_session_json_type,
        json_type(payload, '$.event_properties') as raw_event_properties_json_type,
        json_extract_string(payload, '$.event_name') as raw_event_name,
        json_extract_string(payload, '$.user_id') as raw_user_id,
        json_extract_string(payload, '$.session_id') as raw_session_id,
        json_extract_string(payload, '$.timestamp') as raw_timestamp,
        json_extract_string(payload, '$.platform') as raw_platform,
        json_extract_string(payload, '$.client_version') as raw_client_version,
        json_extract_string(payload, '$.os_version') as raw_os_version,
        json_extract_string(payload, '$.device_model') as raw_device_model,
        json_extract_string(payload, '$.locale') as raw_locale,
        json_extract_string(payload, '$.network_type') as raw_network_type,
        json_extract_string(payload, '$.is_first_session') as raw_is_first_session,
        json_extract_string(payload, '$.session_count') as raw_session_count,
        json_extract(payload, '$.event_properties') as raw_event_properties
    from source
),

normalized as (
    select
        *,
        nullif(trim(raw_event_name), '') as event_name,
        try_cast(nullif(trim(raw_user_id), '') as bigint) as user_id,
        nullif(trim(raw_session_id), '') as session_id,
        case
            when regexp_full_match(trim(raw_timestamp), '[0-9]{13}')
                then to_timestamp(try_cast(trim(raw_timestamp) as double) / 1000.0)
            when regexp_matches(trim(raw_timestamp), '(Z|[+-][0-9]{2}:[0-9]{2})$', 'i')
                then try_cast(trim(raw_timestamp) as timestamptz)
            when nullif(trim(raw_timestamp), '') is not null
                then try_cast(trim(raw_timestamp) || 'Z' as timestamptz)
        end as event_timestamp_utc,
        coalesce(
            nullif(trim(regexp_replace(replace(raw_device_model, chr(160), ' '), '\\s+', ' ', 'g')), ''),
            null
        ) as device_model,
        lower(replace(nullif(trim(raw_locale), ''), '-', '_')) as locale,
        lower(nullif(trim(raw_network_type), '')) as network_type,
        case lower(trim(raw_platform))
            when 'ios' then 'iOS'
            when 'android' then 'Android'
            else nullif(trim(raw_platform), '')
        end as platform,
        nullif(trim(raw_client_version), '') as client_version,
        nullif(trim(raw_os_version), '') as os_version,
        try_cast(nullif(trim(raw_session_count), '') as bigint) as session_count,
        case lower(trim(raw_is_first_session))
            when 'true' then true
            when 'false' then false
        end as is_first_session,
        case
            when nullif(trim(raw_timestamp), '') is not null
             and not regexp_full_match(trim(raw_timestamp), '[0-9]{13}')
             and not regexp_matches(trim(raw_timestamp), '(Z|[+-][0-9]{2}:[0-9]{2})$', 'i')
             and try_cast(trim(raw_timestamp) || 'Z' as timestamptz) is not null
            then true else false
        end as timestamp_timezone_assumed,
        row_number() over (
            partition by source_batch_id, raw_line_hash order by source_line
        ) as exact_duplicate_rank,
        count(*) over (
            partition by source_batch_id, raw_line_hash
        ) as exact_duplicate_count
    from extracted
),

classified as (
    select
        *,
        count(distinct raw_line_hash) over (
            partition by source_batch_id, raw_user_id, raw_session_id, raw_timestamp, raw_event_name
        ) > 1 as has_natural_key_collision,
        event_timestamp_utc >= try_cast('{{ var("launch_window_start") }}' as timestamptz)
        and event_timestamp_utc < try_cast('{{ var("launch_window_end") }}' as timestamptz)
            as is_in_launch_window,
        raw_user_id is not null and user_id is null as user_id_invalid,
        raw_timestamp is not null and event_timestamp_utc is null as timestamp_invalid,
        raw_session_count is not null and session_count is null as session_count_invalid,
        raw_is_first_session is not null and is_first_session is null as is_first_session_invalid
    from normalized
)

select
    *,
    event_name is not null
        and user_id is not null
        and session_id is not null
        and event_timestamp_utc is not null
        and exact_duplicate_rank = 1
        and is_in_launch_window
        as eligible_for_funnel_base
from classified
