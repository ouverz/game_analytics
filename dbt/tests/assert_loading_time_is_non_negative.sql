select session_key, loading_time_ms
from {{ ref('fct_loading_sessions') }}
where loading_time_ms < 0
