select source_batch_id, session_key, step_order, count(*) as row_count
from {{ ref('fct_loading_session_steps') }}
group by 1, 2, 3
having count(*) != 1
