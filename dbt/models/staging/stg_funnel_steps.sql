select
    f.source_batch_id,
    f.source_line,
    f.ingested_at,
    f.raw_line_hash,
    f.source_step_code,
    f.source_sequence,
    try_cast(regexp_extract(trim(f.source_step_code), '^([0-9]+)', 1) as integer) as stage_number,
    nullif(regexp_extract(upper(trim(f.source_step_code)), '^[0-9]+([A-Z]+)$', 1), '') as variant_code,
    nullif(trim(f.event_name), '') as event_name
from {{ source('raw', 'funnel_steps') }} f
inner join {{ source('meta', 'source_batches') }} b using (source_batch_id)
where b.promotion_status = 'promoted'
