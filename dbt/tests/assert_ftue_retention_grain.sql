select
    aggregation_level,
    platform,
    client_version,
    count(*) as duplicate_rows
from {{ ref('mart_ftue_summary') }}
group by 1, 2, 3
having count(*) != 1

union all

select
    'invalid_dimension_population' as aggregation_level,
    platform,
    client_version,
    1 as duplicate_rows
from {{ ref('mart_ftue_summary') }}
where (aggregation_level = 'overall'
       and (platform is not null or client_version is not null))
   or (aggregation_level = 'platform_version'
       and (platform is null or client_version is null))
