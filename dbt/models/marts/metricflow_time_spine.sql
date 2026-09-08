select cast(date_day as timestamp) as date_day
from generate_series(
    timestamp '2026-01-01 00:00:00',
    timestamp '2027-01-01 00:00:00',
    interval 1 day
) as spine(date_day)
