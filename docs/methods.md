# AI Assistance and Independent Verification

## How I used AI

I used AI throughout the project to accelerate development and as a technical
sparring partner. It supported the work, but I remained responsible for the
analytical definitions, design choices, and verification of the results.

Planning was a critical first step. I provided the assignment brief and project
context, asked AI to propose a structured delivery plan, and then challenged and
revised that plan before implementation. Throughout the project, I asked it to
critique my assumptions and proposed design decisions rather than simply agree
with them. I also instructed it to ask questions when something was unclear,
base its recommendations on the available project evidence, and explicitly say
when it lacked the information needed to reach a supported conclusion.

AI assistance was used in the following areas:

- Developing the Python validation and ingestion workflow for the supplied
  JSONL and CSV sources, including quarantine and idempotency behavior.
- Configuring dbt, drafting models, and designing data tests, unit tests, data
  contracts, documentation, and lineage.
- Configuring Superset and creating datasets, charts, dashboard layouts, and a
  shared visual theme through its API.
- Profiling the source data, investigating anomalies, and proposing validation
  and reconciliation checks.
- Drafting and refining project documentation, stakeholder explanations, and
  the data architecture proposal.

Generated code and recommendations were treated as drafts to inspect and test,
not as evidence that the implementation was correct.

## What I verified independently

I manually reviewed the supplied files and representative records to understand
the domain, event structure, and relationships between sources. I then verified
the implementation and results through:

- Python tests covering parsing, ingestion behavior, and metric edge cases.
- dbt contracts, unit tests, relationship tests, and custom business assertions.
- A raw-file reconciliation in `src/reconcile_metrics.py`, implemented
  independently of the dbt marts.
- A direct SQL cross-check of FTUE numerators and timing statistics.
- Live execution of all 12 Superset chart queries against the governed marts and
  visual inspection of the resulting dashboards.

The separate reconciliation was important because validating dbt logic with a
second query built from the same assumptions would not be a meaningful
independent check.

## A decision I did not delegate to AI

I retained ownership of the mandatory loading-funnel definition and the
decision to report patch, privacy, and Apple tracking outcomes using conditional
denominators. Event order alone cannot establish whether a prompt is universally
required, platform-specific, recoverable, or post-entry. Delegating that
semantic decision could have produced a visually plausible but conceptually
incorrect funnel, so I made the final classification using the event context,
observed session behavior, and the assignment's product objective.
