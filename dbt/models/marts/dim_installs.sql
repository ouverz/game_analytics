select
    source_batch_id,
    md5(cast(user_id as varchar)) as user_key,
    install_date,
    platform,
    install_source,
    country
from {{ ref('int_installs') }}
