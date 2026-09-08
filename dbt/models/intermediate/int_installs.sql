select
    source_batch_id,
    user_id,
    install_date,
    platform,
    install_source,
    country
from {{ ref('stg_installs') }}
where user_id is not null
qualify row_number() over (
    partition by source_batch_id, user_id order by source_line
) = 1
