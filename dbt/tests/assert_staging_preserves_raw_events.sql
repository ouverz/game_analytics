with raw_counts as (
    select source_batch_id, count(*) as row_count
    from {{ source('raw', 'events') }}
    group by 1
), staged_counts as (
    select source_batch_id, count(*) as row_count
    from {{ ref('stg_events') }}
    group by 1
)
select coalesce(r.source_batch_id, s.source_batch_id) as source_batch_id
from raw_counts r
full outer join staged_counts s using (source_batch_id)
where coalesce(r.row_count, 0) != coalesce(s.row_count, 0)
