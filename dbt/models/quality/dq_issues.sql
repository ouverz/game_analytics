with event_issues as (
    select source_batch_id, 'events.jsonl' as source_file, source_line,
           'invalid_user_id' as issue_code, 'warning' as severity,
           'user_id' as affected_field, 'value present but not castable' as observed_value_context
    from {{ ref('int_events_enriched') }} where user_id_invalid
    union all
    select source_batch_id, 'events.jsonl', source_line, 'invalid_timestamp', 'warning',
           'timestamp', 'value present but not parseable' from {{ ref('int_events_enriched') }} where timestamp_invalid
    union all
    select source_batch_id, 'events.jsonl', source_line, 'noncanonical_source_type', 'warning',
           'user_id', concat('JSON type=', raw_user_id_json_type)
    from {{ ref('int_events_enriched') }}
    where raw_user_id_json_type not in ('BIGINT', 'UBIGINT', 'INTEGER', 'UINTEGER')
      and raw_user_id_json_type is not null
    union all
    select source_batch_id, 'events.jsonl', source_line, 'noncanonical_source_type', 'warning',
           'session_count', concat('JSON type=', raw_session_count_json_type)
    from {{ ref('int_events_enriched') }}
    where raw_session_count_json_type not in ('BIGINT', 'UBIGINT', 'INTEGER', 'UINTEGER')
      and raw_session_count_json_type is not null
    union all
    select source_batch_id, 'events.jsonl', source_line, 'noncanonical_source_type', 'warning',
           'is_first_session', concat('JSON type=', raw_is_first_session_json_type)
    from {{ ref('int_events_enriched') }}
    where raw_is_first_session_json_type != 'BOOLEAN'
      and raw_is_first_session_json_type is not null
    union all
    select source_batch_id, 'events.jsonl', source_line, 'missing_required_value', 'warning',
           'required_event_field', 'one or more required fields are null or empty'
    from {{ ref('int_events_enriched') }}
    where event_name is null or user_id is null or session_id is null or event_timestamp_utc is null
    union all
    select source_batch_id, 'events.jsonl', source_line, 'exact_duplicate_copy', 'warning',
           'raw_line_hash', 'identical raw record; deterministic later copy'
    from {{ ref('int_events_enriched') }} where exact_duplicate_rank > 1
    union all
    select source_batch_id, 'events.jsonl', source_line, 'natural_key_collision', 'warning',
           'event_natural_key', 'same natural key has differing payloads'
    from {{ ref('int_events_enriched') }} where has_natural_key_collision
    union all
    select source_batch_id, 'events.jsonl', source_line, 'out_of_launch_window', 'warning',
           'timestamp', 'outside configured launch window'
    from {{ ref('int_events_enriched') }} where event_timestamp_utc is not null and not is_in_launch_window
    union all
    select source_batch_id, 'events.jsonl', source_line, 'missing_network_type', 'warning',
           'network_type', case when network_type_is_present then 'explicit null or empty' else 'source key missing' end
    from {{ ref('int_events_enriched') }} where network_type is null
    union all
    select source_batch_id, 'events.jsonl', source_line, 'missing_event_properties', 'warning',
           'event_properties', case when event_properties_is_present then 'explicit null' else 'source key missing' end
    from {{ ref('int_events_enriched') }}
    where not event_properties_is_present or raw_event_properties_json_type = 'NULL'
    union all
    select source_batch_id, 'events.jsonl', source_line, 'category_normalized', 'warning',
           'device_model', 'whitespace normalization applied'
    from {{ ref('int_events_enriched') }} where raw_device_model is distinct from device_model
    union all
    select source_batch_id, 'events.jsonl', source_line, 'category_normalized', 'warning',
           'locale', concat('normalized to ', locale)
    from {{ ref('int_events_enriched') }} where raw_locale is distinct from locale
    union all
    select source_batch_id, 'events.jsonl', source_line, 'category_normalized', 'warning',
           'network_type', concat('normalized to ', network_type)
    from {{ ref('int_events_enriched') }}
    where raw_network_type is not null and raw_network_type is distinct from network_type
    union all
    select source_batch_id, 'events.jsonl', source_line, 'missing_attribution', 'warning',
           'install_attribution', 'no matching install row'
    from {{ ref('int_events_enriched') }} where not has_matching_install
    union all
    select source_batch_id, 'events.jsonl', source_line, 'platform_conflict', 'warning',
           'platform', concat('event=', coalesce(platform, '<null>'), '; install=', coalesce(install_platform, '<null>'))
    from {{ ref('int_events_enriched') }} where has_platform_conflict
    union all
    select source_batch_id, 'events.jsonl', source_line, 'pre_install_event', 'warning',
           'timestamp', 'event calendar date precedes install date'
    from {{ ref('int_events_enriched') }} where is_pre_install_event
    union all
    select source_batch_id, 'events.jsonl', source_line, 'session_metadata_conflict', 'warning',
           'session_count', 'session suffix/count or first-session flag disagrees'
    from {{ ref('int_events_enriched') }} where has_session_count_conflict or has_first_session_conflict
    union all
    select source_batch_id, 'events.jsonl', source_line, 'session_timestamp_order_conflict', 'warning',
           'timestamp', 'session timestamps decrease in source-line order'
    from {{ ref('int_events_enriched') }} where session_has_time_reversal
    union all
    select source_batch_id, 'events.jsonl', source_line, 'platform_inapplicable_event', 'warning',
           'event_name', concat(event_name, ' observed on ', coalesce(platform, '<null>'))
    from {{ ref('int_events_enriched') }} where is_platform_inapplicable
),

structural_issues as (
    select
        source_batch_id,
        source_file,
        source_line,
        rejection_code as issue_code,
        'warning' as severity,
        'record_structure' as affected_field,
        rejection_message as observed_value_context
    from {{ source('raw', 'rejected_records') }}
)

select * from event_issues
union all
select * from structural_issues
