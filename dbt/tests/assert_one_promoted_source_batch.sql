select count(*) as promoted_batches
from {{ source('meta', 'source_batches') }}
where promotion_status = 'promoted'
having count(*) != 1
