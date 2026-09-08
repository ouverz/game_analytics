{{ config(severity='warn') }}

select issue_code, count(*) as issue_count
from {{ ref('dq_issues') }}
group by 1
