select 1 as missing_promoted_batch
where not exists (
    select 1 from {{ source('meta', 'source_batches') }} where promotion_status = 'promoted'
)
