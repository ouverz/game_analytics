# Analytical Methodology and Metric Reference

## Purpose

This document explains how telemetry is converted into governed metrics and
records the principal analytical definitions. Detailed source profiling and
issue-handling decisions are documented in
[data_exploration_and_preparation.md](data_exploration_and_preparation.md). The use
of AI and independent verification are documented separately in
[methods.md](methods.md).

## Analytical workflow

```text
events.jsonl + installs.csv + funnel_steps.csv
                    |
          Python validation and ingestion
                    |
        DuckDB raw + metadata + quarantine
                    |
             dbt staging models
                    |
     canonical events and ordered session steps
                    |
       facts + dimensions + quality models
                    |
          governed analytical KPI marts
              /                 \
    Superset dashboards     dbt metrics/docs
```

The workflow follows these principles:

- Raw inputs are never modified.
- Source batches are content-addressed, and ingestion is idempotent.
- User identifiers and timestamps are normalized before joins or metric logic.
- Required funnel steps are evaluated sequentially within a user session.
- Optional and conditional outcomes retain their own denominators rather than
  being forced into the mandatory funnel.
- Metric logic lives in reviewed dbt models rather than dashboard-specific SQL.
- Published outputs contain aggregates rather than unnecessary user identifiers.

## Metric definitions and boundaries

- **Primary funnel:** session attempts beginning with `INIT_CLIENT_START` and
  ending with `INIT_GAME_JOINED`. Every required event must occur at or after
  the preceding step in the same session.
- **Loading time:** elapsed time from client start to game joined. Twenty-one
  completed sessions with incoherent timestamp order are excluded, leaving 556
  timing-eligible sessions.
- **Conditional-outcome continuation:** affected sessions with a later
  `INIT_GAME_JOINED` event in the same session divided by all sessions observing
  that outcome. Privacy decline and iOS tracking denial are not treated as
  loading abandonment when the session subsequently continues.
- **First-session activation:** a `BATTLE_STARTED` event after sequential game
  entry in the player's first eligible session.
- **D1 retention:** mature installs with an eligible `INIT_CLIENT_START` on the
  exact next UTC calendar day. Installs whose next day is not fully observable
  are excluded.

Tutorial completion, battle retries, progression state, authoritative session
duration, and crash-free onboarding are not reported because the necessary
events or fields are absent. D3 and D7 are deferred because the 14-day snapshot
would leave smaller and less stable mature cohorts.

## Governed models

| Model | Purpose |
| --- | --- |
| `analytics.mart_launch_summary` | Overall loading completion and duration KPIs |
| `analytics.mart_primary_funnel` | Ordered step counts, conversion, and drop-off |
| `analytics.mart_branch_outcomes` | Continuation after conditional decisions or failures |
| `analytics.mart_segment_performance` | Platform and client-version comparisons |
| `analytics.mart_ftue_summary` | First-session entry, activation, time to battle, and mature-cohort D1 retention |

`funnel_steps.csv` is the product-owned ordering of the primary journey. The
analytics-owned semantics in `dbt/seeds/funnel_event_semantics.csv` distinguish
milestones, starts, ends, outcomes, failures, platform-specific branches, and
post-entry diagnostics.
