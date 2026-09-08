select count(*) as observed_count
from {{ ref('stg_funnel_steps') }}
having count(*) != 28
