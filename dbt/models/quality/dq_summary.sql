select
    source_batch_id,
    issue_code,
    severity,
    affected_field,
    count(*) as issue_count,
    count(*)::double / nullif(
        (select count(*) from {{ ref('stg_events') }} e where e.source_batch_id = d.source_batch_id),
        0
    ) as issue_rate_vs_accepted_events
from {{ ref('dq_issues') }} d
group by 1, 2, 3, 4
