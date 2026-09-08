select
    f.source_batch_id,
    f.source_sequence,
    f.source_step_code,
    f.stage_number,
    f.variant_code,
    f.event_name,
    s.logical_step_key,
    s.funnel_section,
    s.event_role,
    s.outcome_value,
    s.applicability,
    s.funnel_scope,
    s.is_primary_endpoint,
    s.is_explicit_failure,
    s.primary_step_order,
    s.primary_step_name,
    s.branch_order,
    s.branch_name,
    s.primary_step_order is not null as is_primary_step,
    coalesce(s.primary_step_order = min(s.primary_step_order) filter (
        where s.primary_step_order is not null
    ) over (partition by f.source_batch_id), false) as is_funnel_start,
    coalesce(s.primary_step_order = max(s.primary_step_order) filter (
        where s.primary_step_order is not null
    ) over (partition by f.source_batch_id), false) as is_funnel_end
from {{ ref('stg_funnel_steps') }} f
inner join {{ ref('funnel_event_semantics') }} s using (event_name)
