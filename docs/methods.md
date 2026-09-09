# Methods: Use of AI

## How I used AI

I used AI throughout the project to accelerate planning, implementation,
testing, analysis, and documentation. I treated it as a technical sparring
partner rather than an autonomous decision-maker.

AI helped implement:

- Python ingestion, normalization, and quarantine handling for the supplied
  sources;
- dbt configuration, models, contracts, tests, metrics, and lineage;
- Superset deployment, API configuration, datasets, charts, and dashboards;
- data profiling, reconciliation, and investigation of quality issues; and
- the stakeholder brief, README, technical documentation, and architecture
  proposal.

## What I explicitly proposed or decided

I recommended Python with DuckDB and dbt as the core local analytical workflow,
and selected Superset instead of Streamlit as the visualization layer. AI then
helped configure and implement that stack.

I supplied the assignment brief and asked AI to develop an initial plan, explain
its assumptions, ask questions when information was missing, and challenge my
ideas when appropriate. I retained control over priorities, scope, analytical
framing, and the form of the final deliverables.

## How I challenged or redirected AI

I redirected the work when it became too complex or moved beyond the assignment.
I stopped an increasingly extensive implementation and required the work to
focus first on a reproducible minimum viable Part 1 submission, followed by the
Part 2 proposal. Further engineering was deferred unless needed for that result.

I also challenged unclear or weak conclusions, including:

- why D1 retention was included in the FTUE analysis;
- how conditional outcomes differed from mandatory funnel steps;
- whether dbt lineage represented a genuine raw-to-mart dependency chain;
- whether the architecture remained practical at different traffic levels; and
- whether the proposed architecture satisfied every requirement in the brief.

## What I reviewed independently

I reviewed the outputs rather than accepting generated results at face value. I
identified that the primary Superset funnel displayed its steps in the wrong
order and inspected its underlying query, which lacked the required ordering. I
also reviewed dashboard screenshots, questioned redundant tables and unclear
labels, and requested clearer conversion visuals.

I questioned whether retention belonged in the loading-funnel analysis and
decided that technical loading and FTUE should be presented as separate
dashboards. I then required both dashboards to use consistent layout,
typography, terminology, and colors.

I repeatedly reviewed the documentation and architecture, removing content that
was excessive, outside scope, or incorrectly presented supporting artifacts as
core deliverables.

## How technical results were validated

AI executed the automated validation, including Python tests, dbt tests and
contracts, source-to-mart reconciliation, direct SQL checks, Superset chart
queries, and clean-environment reproduction checks. I reviewed the reported
outcomes and requested further investigation when results, lineage, dashboard
behavior, or explanations were unclear. I do not claim to have independently
reimplemented or manually executed every validation.

## Decisions I did not leave to AI

I retained final responsibility for product scope and analytical presentation.
The principal decisions I did not leave to AI were:

- selecting Python, DuckDB, dbt, and Superset as the main local components;
- prioritizing a reproducible minimum viable submission over further
  engineering;
- treating `funnel_steps.csv` as the product-owned journey mapping and requiring
  governed metrics to be defined once rather than recalculated in dashboards;
- separating technical loading performance from FTUE and retention;
- requiring consistent visual design across the two dashboards; and
- keeping the architecture practical, maintainable, and limited to the brief.

These decisions required product judgement, awareness of the assignment's time
constraint, and consideration of how stakeholders would interpret the final
deliverables.
