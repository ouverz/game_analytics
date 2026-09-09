# Data Exploration, Preparation, and Ingestion Decisions

## Purpose

This document explains how the three supplied datasets were explored, what the
initial profiling revealed, and how those findings shaped the ingestion and
transformation design. Its focus is not only on which records are imperfect,
but on why each issue is rejected, normalized, flagged, or excluded from a
specific metric.

The central design principle is **preserve first, classify second, and exclude
only where an issue invalidates a particular calculation**. A malformed JSON
record cannot safely enter the event table. A valid event with missing optional
network metadata can. A session whose timestamps move backwards can support a
funnel count, but not a duration percentile. Keeping those cases separate
prevents a small number of defects from either stopping the whole pipeline or
silently biasing every metric.

The figures below describe the supplied 14-day assignment snapshot and can be
reproduced by running the build and querying the dbt quality models.

## Source inventory and analytical roles

| Source | Observed input | Role | Grain after structural ingestion |
| --- | ---: | --- | --- |
| `events.jsonl` | 18,479 physical lines | Client telemetry for loading, gameplay, and return behavior | One structurally valid JSON object per source line |
| `installs.csv` | 101 data rows | Install date, platform, acquisition source, and country | One source row per installed user |
| `funnel_steps.csv` | 28 data rows | Product-owned ordering of loading events and variants | One configured event per source row |

The event input contains 102 distinct parseable user identifiers, 623 sessions
with at least one metric-eligible event, and 36 event names. The install input
contains 101 unique users across two platforms, three acquisition sources,
eight countries, and install dates from 9 through 22 June 2026.

The apparent user-count mismatch was an early signal that install attribution
could not be assumed to be complete. The model therefore uses a left join from
events to installs and records missing attribution instead of dropping the
event at join time.

## Exploratory analysis approach

Exploration was organized around questions that could change a metric or a
pipeline decision, rather than around charts alone:

1. **Can each physical record be read safely?** Files were checked for presence,
   non-empty UTF-8 content, exact CSV headers and widths, valid JSON syntax, and
   object-shaped JSONL values.
2. **Can important fields be interpreted consistently?** Profiling covered
   identifier types, required-field completeness, timestamp shapes, Boolean and
   integer representations, platform labels, locale formatting, whitespace,
   and optional properties.
3. **Are event entities internally coherent?** Checks covered exact duplicate
   payloads, same-natural-key/different-payload collisions, session sequence,
   session metadata, platform applicability, install joins, and event dates
   relative to install dates.
4. **Does the observed journey match the product-owned funnel?** Event names
   were reconciled to `funnel_steps.csv`, then classified as required loading
   steps, conditional outcomes, failures, or post-entry diagnostics.
5. **Which anomalies affect which measures?** Funnel membership, timing,
   install segmentation, FTUE, and retention were considered separately.
6. **Do independently implemented results agree?** Headline and quality totals
   were recalculated directly from the raw files in
   [`src/reconcile_metrics.py`](../src/reconcile_metrics.py), independently of
   the dbt marts.

The exploratory work is operationalized in reproducible assets rather than a
one-off notebook: [`dq_issues.sql`](../dbt/models/quality/dq_issues.sql) produces
row-level issue flags, [`dq_summary.sql`](../dbt/models/quality/dq_summary.sql)
aggregates them, dbt tests enforce invariants, and
[`metric_reconciliation.json`](../outputs/metric_reconciliation.json) captures
the independent aggregate result.

## Initial data-quality findings

### Structural and metric eligibility waterfall

| Stage | Rows retained | Rows removed at stage | Treatment |
| --- | ---: | ---: | --- |
| Physical event lines | 18,479 | — | Immutable source input |
| Valid JSON objects | 18,476 | 3 | Malformed JSON lines quarantined |
| First copy of exact payload | 18,406 | 70 | Later identical copies excluded from metrics |
| Inside launch window | 18,400 | 6 | Future-dated rows excluded from launch metrics |
| Metric-eligible events | 18,400 | 0 additional | Required fields were complete and parseable in all structurally valid rows |

The three malformed rows are structural failures, while duplicates and date
window violations are analytical eligibility failures. That distinction is
important: all 18,476 valid JSON objects remain available in source-faithful
staging, including the 76 rows not used in the published launch metrics.

### Detailed observations

Issue counts below are counts of affected event rows unless a session or user
count is stated. A row may carry more than one issue flag, so the counts must
not be added to produce a rejected-record total.

| Observation | Evidence | Interpretation and current treatment |
| --- | --- | --- |
| Malformed JSON | 3 of 18,479 physical lines (0.016%) | Quarantined because the payload cannot be interpreted safely. The remaining batch is promoted in quarantine mode. |
| Exact duplicate copies | 70 later copies in 64 duplicate groups, across 61 sessions and 34 users | Only the earliest source-line copy is metric-eligible. Raw lineage and duplicate rank are retained. |
| Natural-key collisions | None found | The check remains because equal user/session/timestamp/event keys with differing payloads are not safe to treat as exact duplicates. |
| Outside launch window | 6 events dated 15–20 January 2027 | Preserved in staging and flagged; excluded from the configured half-open launch window `[2026-06-09, 2026-06-23)` UTC. |
| Timestamp formats | 18,347 values with explicit timezone, 83 epoch-millisecond values, and 46 parseable values without timezone | Parsed with `try_cast`; missing timezone is explicitly assumed to be UTC and flagged. No structurally valid timestamp failed parsing. |
| Noncanonical JSON types | 12 string user IDs, 24 string session counts, and 17 string first-session flags | Safely coerced to the canonical type while preserving the raw JSON type for audit. |
| Category formatting | All 18,476 locale values normalized; 60 device-model values had whitespace normalized; 14 network labels normalized | Locale is lowercased and `-` becomes `_`; repeated/NBSP whitespace is collapsed; platform/network labels are canonicalized. Raw values remain available. |
| Missing optional metadata | 88 rows have no usable network type; 9 have null event properties | Flagged but retained because neither field is required for the submitted funnel or FTUE metrics. Missing keys and explicit nulls remain distinguishable. |
| Missing required event values | None among valid JSON objects | The eligibility rule still requires event name, user ID, session ID, and timestamp so future batches fail safely at the metric boundary. |
| Missing install attribution | 10 event rows, one session, one user | Overall technical funnel eligibility is retained; install-based platform/version segmentation is disabled for the affected session. |
| Event/install platform conflict | 19 event rows, one session, one user | Retained in overall funnel counts but excluded from attribution-dependent segment cuts to avoid assigning the attempt to a disputed platform. |
| Events before install date | 438 rows, 16 sessions, nine users; affected sessions start 1–10 days before the recorded install date | Flagged as an upstream chronology issue. The current technical funnel retains these attempts because their event sequence is still observable. This remains a caveat for install-cohort and FTUE interpretation and should be sensitivity-tested before production use. |
| Session metadata conflicts | 547 rows, 19 sessions, seven users | Session-ID suffix, `session_count`, or `is_first_session` disagree. The raw attributes are retained, while FTUE identifies the first session from the earliest eligible client-start timestamp instead of trusting the conflicting flag. |
| Timestamp reversals | 717 rows, 25 sessions, 15 users | Session membership and ordered funnel counts are retained, but the entire affected session is ineligible for elapsed-time metrics. Of 577 completed launches, 21 have a reversal, leaving 556 timing-eligible sessions. |
| Platform-inapplicable event | 12 Android rows contain `APPLE_TRACKING_STATUS_AUTHORIZED` | Flagged as an instrumentation/semantic mismatch. It is not part of the required primary funnel and does not determine funnel completion. |

The installs file itself had no invalid user IDs, invalid dates, or duplicate
user rows. The funnel file had 28 distinct event names and 28 distinct step
codes covering stages 1–21; variants explain why the row count is greater than
the number of primary mandatory steps.

## Analytical findings and outliers from exploration

Data-quality profiling was followed by behavioral profiling. These are product
signals rather than ingestion defects, although some identify where additional
telemetry is needed.

### Loading journey

- 621 of 623 event-bearing sessions contain the required `INIT_CLIENT_START`
  funnel entry. The two sessions without it are retained as event history but
  do not enter the primary funnel denominator.
- 577 of 621 started sessions reach `INIT_GAME_JOINED` sequentially, a 92.9%
  completion rate.
- The largest transition loss is 32 sessions between maintenance check and
  data-load start. A further 11 sessions are lost between data-load start and
  completion, and one between ready-to-start and login start.
- Explicit failure/decision branches clarify some, but not all, loss. None of
  the 11 maintenance-blocked, three patch-failed, or ten data-load-failed
  sessions continues to game entry in the same session. Patch decline is only
  partly terminal: eight of 16 sessions continue.
- Privacy decline and iOS tracking denial are not abandonment signals in this
  sample: all 63 privacy-declined and all 54 tracking-denied sessions continue.
  This is why these outcomes are shown as conditional branches rather than
  mandatory funnel stages.

### Loading-time distribution

Among the 556 completed sessions with coherent timestamp order, elapsed loading
time ranges from 10.8 to 365.1 seconds. The median is 105.4 seconds, P90 is
156.2 seconds, and P95 is 191.9 seconds. The long upper tail is operationally
important: completion alone would make the loading experience look healthier
than the wait-time distribution suggests.

Segment observations are directional because sample sizes differ materially.
Android 1.0.2 is the strongest observed group at 201/211 completion (95.3%) and
a 95.7-second median. iOS 1.0.2 is the weakest at 19/23 (82.6%), but 23 starts
are too few to establish a version effect. Platform/version differences were
therefore surfaced for investigation rather than treated as causal evidence or
release gates.

### FTUE observations

The source has no tutorial-step or tutorial-completion events. FTUE was
therefore bounded to defensible observable outcomes:

- 86 of 101 players enter the game in their first observed eligible session
  (85.1%).
- 43 of 101 start a battle after sequential game entry in that session (42.6%);
  this is 50.0% of first-session entrants.
- For those 43 activated players, median time from client start to first battle
  is 10.1 minutes and P90 is 23.0 minutes. This combines technical loading and
  the uninstrumented post-entry path, so it is a time-to-value measure rather
  than a pure loading measure.
- Exact-day D1 retention is 45 of 93 mature installs (48.4%). It is an early
  outcome benchmark, not evidence that a particular FTUE step caused return.

The nine users with pre-install telemetry are a known sensitivity concern for
install-cohort analysis. The present model keeps the supplied install entity
and records the chronology warning instead of inventing a corrected install
date. Before production decision-making, the source-of-truth definition of an
install should be resolved and the FTUE/D1 results recalculated with and without
those users.

## Preparation and transformation design

### 1. Content-addressed, atomic ingestion

Each of the three input files is hashed with SHA-256. Their hashes form a
deterministic batch identifier, and every execution receives a separate run
identifier. The raw rows, batch metadata, reject records, and run audit are
written in one DuckDB transaction.

This provides four safeguards:

- rerunning unchanged files records another execution without duplicating raw
  rows;
- a changed source produces a new immutable batch rather than overwriting the
  old one;
- only batches marked `promoted` are visible to dbt staging models; and
- a failure rolls back the transaction instead of leaving a partly loaded
  batch.

The behavior is implemented in
[`src/game_analytics/ingestion.py`](../src/game_analytics/ingestion.py) and
covered by focused tests in
[`tests/test_ingestion.py`](../tests/test_ingestion.py).

### 2. Strict and quarantine operating modes

Two modes support different operational needs:

- **Quarantine mode** is the normal analytical build. Structurally bad rows are
  written to `raw.rejected_records`, while structurally sound rows are promoted.
  This allows a small, understood reject rate to remain observable without
  blocking all analysis.
- **Strict mode** is a fail-fast validation gate. Any structural rejection
  makes the execution fail and prevents a new batch from being promoted. It is
  useful for upstream contract testing and production acceptance checks.

An unreadable/empty/non-UTF-8 file, malformed CSV, or incorrect CSV header makes
the whole source file unusable in either mode. A single bad-width CSV row or
malformed JSONL line is row-addressable and can be quarantined. This boundary
avoids promoting a file whose columns may have shifted while still allowing
isolated records to be diagnosed.

### 3. Source-faithful raw storage and reversible normalization

Raw event payloads are stored as JSON together with source batch, line number,
ingestion timestamp, and raw-line hash. CSV values remain strings in raw tables.
Type conversion occurs in dbt staging with `try_cast`, so an unexpected value
becomes a visible null/flag rather than crashing the entire model.

Canonical values sit beside raw values and provenance. This makes every cleanup
reversible and inspectable:

- timestamps become UTC-aware values;
- numeric and Boolean strings are safely coerced;
- `ios`/`android`, locale, network, and whitespace variations are normalized;
- JSON key presence is retained separately from its extracted value; and
- duplicate ranks and launch-window eligibility are materialized explicitly.

### 4. Metric-specific eligibility instead of one global “clean” flag

One universal clean/not-clean classification would discard useful evidence or
allow invalid calculations. The enriched event model therefore exposes several
eligibility boundaries:

| Eligibility boundary | Required conditions | Used for |
| --- | --- | --- |
| Funnel base | Required fields parse, first exact copy, inside launch window | Sequential funnel and event-level facts |
| Install segmentation | Funnel base, matching install, no platform conflict | Platform/version and attribution cuts |
| Timing | Funnel base and no source-order timestamp reversal in the session | Loading duration percentiles |
| D1 maturity | Install's next UTC day is fully inside the observation window | Exact-day retention denominator |

This means an optional-field omission does not erase a valid launch attempt,
and a timestamp-order defect cannot generate a negative or misleading loading
duration.

### 5. Sequential funnel reconstruction

The supplied funnel file contains both mandatory milestones and variants. A
governed semantic seed classifies each event's role and platform applicability.
The primary funnel uses ten required steps. For every eligible session, the
model creates a session-by-step grid and marks a step reached only when the
previous required step was reached and the current timestamp is not earlier.

This prevents an isolated late-stage event, replayed telemetry, or out-of-order
payload from falsely implying full conversion. Each step uses its earliest
eligible timestamp, so repeated occurrences do not multiply a session count.
Conditional decisions and failures keep their own observed-session denominator
and are never inserted into the mandatory path.

### 6. Privacy-aware analytical outputs

Raw user IDs are needed locally to join events and installs, but published fact
tables use deterministic hashed user and session keys. Dashboards consume only
aggregated, governed marts. User-level source inputs, local databases, reject
payloads, and environment files are excluded from version control.

## Decision matrix for issue handling

| Issue class | Stop file/batch? | Preserve raw? | Exclude from metrics? | Rationale |
| --- | --- | --- | --- | --- |
| Missing/unreadable file, wrong CSV header, unreadable CSV | Yes | Reject metadata where possible | Entire source unavailable | Record boundaries or schema cannot be trusted |
| Malformed JSONL or bad CSV row width | Strict: yes; quarantine: row only | Yes, in reject table | Affected row | Defect is isolated to a physical record |
| Missing/unparseable required event field | No structural stop | Yes | Funnel base | Event cannot be assigned safely to the journey |
| Exact duplicate | No | Yes | Later copies | Prevent double counting without losing lineage |
| Outside launch window | No | Yes | Launch metrics | Preserve unexpected telemetry for investigation |
| Optional metadata missing | No | Yes | Only metrics that require that field | Avoid unnecessary loss of otherwise valid events |
| Missing install or platform disagreement | No | Yes | Attribution-dependent segmentation | Overall attempt remains valid; segment assignment does not |
| Timestamp reversal | No | Yes | Duration only | Counts can be valid even when elapsed time is not |
| Session metadata disagreement | No | Yes | Do not trust conflicting first-session flag | Derive first session consistently from event chronology |
| Pre-install telemetry | No | Yes | Currently flagged, not globally excluded | Avoid inventing corrected dates; expose as a cohort-analysis caveat |

## Validation and monitoring controls

The pipeline checks its assumptions at several levels:

- Python unit tests exercise structural parsing, strict/quarantine behavior,
  bad CSV headers and widths, transaction-safe promotion, and idempotent reruns.
- dbt schema tests enforce not-null, unique, relationship, accepted-value, and
  model-contract expectations.
- Custom business assertions verify a promoted batch, all 28 configured funnel
  mappings, canonical primary steps, staging preservation, sequential funnel
  monotonicity, timing non-negativity, fact grain, metric projection agreement,
  and FTUE reconciliation.
- A deliberate warning test summarizes known quality flags without converting
  all warnings into pipeline failures.
- The independent raw-file implementation recalculates the quality waterfall
  and published KPIs without querying the dbt marts.

In a production version, these controls should be supplemented with thresholds:
reject rate, duplicate rate, missing-attribution rate, timestamp-reversal
sessions, future-event rate, event-volume drift, and funnel-mapping coverage.
Warnings should become blocking errors only when a documented threshold or
consumer contract is breached.

## Known limitations and recommended follow-up

1. **Resolve pre-install chronology.** Confirm whether `install_date` is the
   authoritative first install, an attribution date, or a refreshed install.
   Publish a sensitivity comparison before using cohort results as a release
   gate.
2. **Improve timestamp contracts.** Require explicit UTC/offset timestamps at
   collection and attach device/server receive time so order conflicts can be
   diagnosed instead of simply excluded from duration.
3. **Fix platform-specific instrumentation.** Prevent Apple tracking events on
   Android and add an automated applicability threshold.
4. **Make loading exits observable.** Add terminal reason/error events between
   maintenance and data-load start, the largest unexplained loss point.
5. **Add stable event identifiers.** A producer-generated event ID would make
   deduplication safer than payload hashing and would separate retries from true
   duplicate delivery.
6. **Instrument tutorial progression.** Explicit tutorial start, step,
   completion, skip, failure, and retry events are required to move beyond the
   current entry/battle proxy for FTUE.
7. **Retain privacy boundaries in production.** Quarantine payload access should
   be restricted, retention-limited, and monitored; published layers should
   continue to use pseudonymous keys and aggregates.

## Reproducing the evidence

From the repository root:

```bash
# Install the locked environment.
uv sync --locked

# Ingest the supplied files in quarantine mode, build all models, and run tests.
uv run game-analytics build --database data/superset_analytics.duckdb

# Recalculate aggregate results directly from the source files.
uv run python src/reconcile_metrics.py

# Demonstrate the fail-fast structural gate; non-zero is expected for this input.
uv run game-analytics ingest --mode strict
```

After the build, inspect `analytics.dq_summary` for aggregate issue counts and
`analytics.dq_issues` for source-line-level diagnostics. The latter may contain
source metadata and should remain in the restricted local database rather than
being exported as a public deliverable.
