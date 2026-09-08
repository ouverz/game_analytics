with overall as (
    select d1_mature_installs, d1_returned_players
    from {{ ref('mart_ftue_summary') }}
    where aggregation_level = 'overall'
),

segments as (
    select
        sum(d1_mature_installs) as d1_mature_installs,
        sum(d1_returned_players) as d1_returned_players
    from {{ ref('mart_ftue_summary') }}
    where aggregation_level = 'platform_version'
)

select overall.*
from overall
cross join segments
where overall.d1_mature_installs != segments.d1_mature_installs
   or overall.d1_returned_players != segments.d1_returned_players
