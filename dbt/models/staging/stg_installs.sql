select
    i.source_batch_id,
    i.source_line,
    i.ingested_at,
    i.raw_line_hash,
    i.user_id as raw_user_id,
    i.install_date as raw_install_date,
    i.platform as raw_platform,
    i.install_source as raw_install_source,
    i.country as raw_country,
    try_cast(nullif(trim(i.user_id), '') as bigint) as user_id,
    try_cast(nullif(trim(i.install_date), '') as date) as install_date,
    case lower(trim(i.platform))
        when 'ios' then 'iOS'
        when 'android' then 'Android'
        else nullif(trim(i.platform), '')
    end as platform,
    lower(nullif(trim(i.install_source), '')) as install_source,
    upper(nullif(trim(i.country), '')) as country,
    i.user_id is not null and try_cast(nullif(trim(i.user_id), '') as bigint) is null as user_id_invalid,
    i.install_date is not null and try_cast(nullif(trim(i.install_date), '') as date) is null as install_date_invalid
from {{ source('raw', 'installs') }} i
inner join {{ source('meta', 'source_batches') }} b using (source_batch_id)
where b.promotion_status = 'promoted'
