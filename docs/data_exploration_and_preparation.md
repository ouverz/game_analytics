# Data Exploration and Preparation

## Purpose and scope

This document describes the work performed on the three supplied assignment
files: how they were explored, which issues were found, and how the data was
prepared so it could be analysed reliably. It covers the implemented local
workflow, not a hypothetical production ingestion platform.

The guiding principle was **preserve first, classify second, and exclude only
where an issue invalidates a calculation**. A malformed JSON record cannot enter
the event table safely. A valid event with missing optional network metadata
can. A session whose timestamps move backwards can support funnel counts but not
duration percentiles. Separating those cases prevents a small number of defects
from either stopping the analysis or silently biasing every metric.

## Source inventory

| Source | Observed input | Analytical role |
| --- | ---: | --- |
| `events.jsonl` | 18,479 physical lines | Loading, gameplay, and return telemetry |
| `installs.csv` | 101 data rows | Install date, platform, acquisition source, and country |
| `funnel_steps.csv` | 28 data rows | Product-owned ordering of loading events and variants |

The parseable event data contains 102 user identifiers, 623 event-bearing
sessions, and 36 event names. Installs contains 101 unique users across two
platforms, three acquisition sources, eight countries, and install dates from 9
through 22 June 2026.

The user-count mismatch showed that install attribution could not be assumed to
be complete. Events are therefore left joined to installs, and missing
attribution is recorded rather than causing otherwise usable telemetry to be
dropped.

## Exploration approach

Exploration focused on questions capable of changing a metric or preparation
decision:

1. **Can every physical record be read?** Files were checked for presence,
   non-empty UTF-8 content, exact CSV headers and widths, valid JSON syntax, and
   object-shaped JSONL values.
2. **Can fields be interpreted consistently?** Profiling covered identifier
   types, required-field completeness, timestamp forms, Boolean and integer
   representations, platform labels, locale formatting, whitespace, and
   optional properties.
3. **Are entities internally coherent?** Checks covered exact duplicate
   payloads, natural-key collisions, session sequence and metadata, platform
   applicability, install joins, and event dates relative to install dates.
4. **Does telemetry match the configured journey?** Event names were reconciled
   to `funnel_steps.csv` and classified as required milestones, conditional
   outcomes, failures, or post-entry diagnostics.
5. **Which anomalies affect which measures?** Funnel membership, timing,
   install segmentation, FTUE, and retention were evaluated separately.
6. **Do independent implementations agree?** Headline and quality totals were
   recalculated directly from the files by
   [`src/reconcile_metrics.py`](../src/reconcile_metrics.py), independently of
   the dbt marts.

The work is reproducible rather than notebook-only:
[`dq_issues.sql`](../dbt/models/quality/dq_issues.sql) produces row-level issue
flags, [`dq_summary.sql`](../dbt/models/quality/dq_summary.sql) aggregates them,
dbt tests enforce invariants, and
[`metric_reconciliation.json`](../outputs/metric_reconciliation.json) records
the independent aggregate result.

## Issues identified

### Structural and analytical eligibility waterfall

| Stage | Rows retained | Removed at stage | Treatment |
| --- | ---: | ---: | --- |
| Physical event lines | 18,479 | — | Preserved source input |
| Valid JSON objects | 18,476 | 3 | Malformed JSON lines quarantined |
| First copy of exact payload | 18,406 | 70 | Later identical copies excluded from metrics |
| Inside launch window | 18,400 | 6 | Future-dated rows excluded from launch metrics |
| Metric-eligible events | 18,400 | 0 additional | Required fields were complete and parseable |

Structural failures and analytical exclusions were kept distinct. All 18,476
valid JSON objects remain available in source-faithful staging, including the 76
rows excluded from published launch metrics.

### Detailed findings and treatment

Counts below are affected event rows unless a session or user count is stated.
One row can carry multiple issue flags, so counts should not be summed.

| Observation | Evidence | Preparation decision |
| --- | --- | --- |
| Malformed JSON | 3 of 18,479 lines (0.016%) | Quarantine the unreadable rows and retain their source-line metadata. |
| Exact duplicate copies | 70 later copies in 64 groups, across 61 sessions and 34 users | Keep only the earliest source-line copy metric-eligible; retain duplicate rank. |
| Natural-key collisions | None found | Keep the check because same key/different payload records are not safe exact duplicates. |
| Outside launch window | 6 events dated 15–20 January 2027 | Preserve and flag; exclude from `[2026-06-09, 2026-06-23)` UTC launch metrics. |
| Timestamp formats | 18,347 offset values, 83 epoch-millisecond values, and 46 timezone-naive values | Parse safely; assume UTC only for timezone-naive values and flag that assumption. |
| Noncanonical types | 12 string user IDs, 24 string session counts, and 17 string first-session flags | Coerce safely while retaining original JSON type and value. |
| Category formatting | All locale values normalized; 60 device models and 14 network labels required normalization | Canonicalize locale, whitespace, platform, and network labels beside raw values. |
| Missing optional metadata | 88 rows lack usable network type; 9 have null event properties | Flag but retain because submitted metrics do not require these fields. |
| Missing required event values | None among valid objects | Continue requiring event name, user ID, session ID, and timestamp at the metric boundary. |
| Missing install attribution | 10 rows, one session, one user | Retain overall funnel eligibility; disable install-dependent segmentation. |
| Event/install platform conflict | 19 rows, one session, one user | Retain overall funnel counts but exclude the disputed segment assignment. |
| Events before install date | 438 rows, 16 sessions, nine users | Flag; retain technical attempts, but treat install-cohort and FTUE results as sensitive to this issue. |
| Session metadata conflicts | 547 rows, 19 sessions, seven users | Derive first session from earliest eligible client start rather than trusting conflicting flags. |
| Timestamp reversals | 717 rows, 25 sessions, 15 users | Retain funnel membership; exclude the affected session from elapsed-time measures. |
| Platform-inapplicable event | 12 Android rows contain an Apple tracking event | Flag as an instrumentation mismatch; do not use it to determine primary-funnel completion. |

The installs file had no invalid user IDs, invalid dates, or duplicate user rows.
The funnel file had 28 unique event names and step codes across stages 1–21;
variants explain why it contains more rows than the ten mandatory milestones.

## Preparation and transformation choices

### Safe structural loading

The local loader hashes all three inputs to form a deterministic batch ID. Raw
rows, run metadata, and rejected-record metadata are written in one DuckDB
transaction. Rerunning unchanged inputs does not duplicate raw rows, changed
files create a new batch, and a failed transaction cannot leave a partially
promoted batch.

Quarantine mode permits isolated malformed lines to be recorded while promoting
structurally valid records. Strict mode fails the batch when any structural row
is rejected. An unreadable file, invalid CSV header, or other defect that makes
record boundaries unreliable stops either mode.

These implemented behaviors are in
[`ingestion.py`](../src/game_analytics/ingestion.py) and are covered by
[`test_ingestion.py`](../tests/test_ingestion.py).

### Reversible type and value normalization

Raw JSON payloads retain batch, source-line, timestamp, and hash provenance;
raw CSV values remain strings. dbt staging applies safe casts so an unexpected
value becomes a visible null or issue flag rather than terminating every model.
Canonical columns sit beside raw evidence:

- timestamps are converted to a consistent UTC representation;
- numeric and Boolean strings are safely coerced;
- platform, locale, network, and whitespace variants are normalized;
- missing JSON keys remain distinguishable from explicit nulls; and
- duplicate rank and launch-window eligibility are materialized explicitly.

### Metric-specific eligibility

A single clean/not-clean flag would either discard useful evidence or admit
invalid calculations. The enriched model therefore applies separate boundaries:

| Boundary | Required conditions | Used for |
| --- | --- | --- |
| Funnel base | Required fields parse, first exact copy, inside launch window | Sequential funnel and event facts |
| Install segmentation | Funnel base, matching install, no platform conflict | Platform/version and attribution cuts |
| Timing | Funnel base and no session timestamp reversal | Loading-duration percentiles |
| D1 maturity | Install's next UTC day is fully observable | Exact-day retention denominator |

This lets an optional-field omission coexist with a valid launch attempt while
preventing a timestamp defect from creating a misleading duration.

### Sequential journey reconstruction

The configured funnel contains mandatory milestones and variants. A governed
semantic seed identifies each role and its platform applicability. For every
eligible session, a required step is reached only after the preceding step and
at a non-earlier timestamp. Repeated events use their earliest eligible
occurrence. Conditional decisions and failures retain their own observed-session
denominators instead of being inserted into the mandatory path.

### Privacy-aware outputs

Raw user IDs are required locally for joins, but published facts use deterministic
hashed user and session keys. Dashboards read aggregate marts. Source inputs,
local databases, rejected payloads, and environment files are excluded from
version control.

## Analytical observations from exploration

The following are product signals, not ingestion defects:

- 577 of 621 started sessions reach `INIT_GAME_JOINED` sequentially (92.9%).
  The largest transition loss is 32 sessions between maintenance check and
  data-load start.
- None of the 11 maintenance-blocked, three patch-failed, or ten
  data-load-failed sessions reaches game entry in the same session. Eight of 16
  patch-declined sessions recover. All 63 privacy-declined and 54
  tracking-denied sessions continue, supporting their treatment as conditional
  outcomes rather than mandatory stages.
- Among 556 completed sessions with coherent timestamp order, median load time
  is 105.4 seconds, P90 is 156.2 seconds, and P95 is 191.9 seconds.
- First-session entry is 86/101 (85.1%), battle activation is 43/101 (42.6%),
  and exact-day D1 retention is 45/93 mature installs (48.4%). Because tutorial
  events are absent, battle start is an observable activation proxy rather than
  tutorial completion.

Platform/version differences and the nine users with pre-install telemetry are
surfaced for investigation, not treated as causal findings or release gates.
Full product interpretation is in the
[stakeholder brief](stakeholder_brief.md).

## Known limitations and follow-up

1. Confirm whether `install_date` means first install, attribution date, or a
   refreshed install, then sensitivity-test FTUE and retention.
2. Require explicit UTC/offset timestamps and add server-receive time so order
   conflicts can be diagnosed.
3. Prevent Apple tracking events on Android and monitor platform applicability.
4. Instrument terminal reasons between maintenance and data-load start.
5. Add producer-generated event IDs to distinguish retries from true duplicates.
6. Add tutorial start, step, completion, skip, failure, and retry events.

## Reproducing the evidence

Follow the standard build and reconciliation steps in the
[README](../README.md). After building, query `analytics.dq_summary` for issue
counts and `analytics.dq_issues` for source-line diagnostics. The latter may
contain source metadata and should remain in the restricted local database.
