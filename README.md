# Mobile Game Technical Launch Analytics

This project evaluates the first 14 days of a mobile strategy game's controlled
technical launch. It turns raw client telemetry, install attribution, and a
product-owned loading sequence into governed metrics, two interactive Apache
Superset dashboards, and a product-facing launch recommendation.

The repository is also a small reference implementation of a trustworthy local
analytics workflow: Python validates and ingests the source files, DuckDB stores
the local data, dbt defines and tests the analytical models, and Superset
presents only governed marts. A separate architecture proposal explains how the
same principles could evolve into an AWS platform processing approximately
1 TB/day.

## What this project answers

The analysis focuses on four practical launch questions:

1. Can a player move through the required loading sequence and enter the game?
2. Where do sessions stop, fail, or take an optional path?
3. How long does a successful launch take, and do platform or client-version
   differences warrant investigation?
4. Does the first-time user experience (FTUE) lead to a first battle and an
   exact-day D1 return?

The primary deliverable is the loading-funnel dashboard. The FTUE dashboard is a
focused companion view; it does not invent tutorial or progression metrics that
the supplied telemetry cannot support.

## Key findings

| Signal | Result | Why it matters |
| --- | ---: | --- |
| Loading-funnel completion | 577 / 621 sessions (92.9%) | Most launch attempts reach the game, but 44 do not complete the required sequence. |
| Median successful load | 105.4 seconds | A typical successful player waits about 1 minute 45 seconds. |
| P90 successful load | 156.2 seconds | One in ten measured successful loads takes more than 2 minutes 36 seconds. |
| Largest transition loss | 32 sessions | The largest loss occurs after maintenance check and before data loading starts. |
| First-session game entry | 86 / 101 players (85.1%) | The new-player view is weaker than the all-attempt funnel because later retries can recover. |
| First-session battle activation | 43 / 101 players (42.6%) | Fewer than half of new players reach the selected core-loop milestone in their first session. |
| Exact-day D1 retention | 45 / 93 mature installs (48.4%) | This is an early outcome benchmark, not causal proof that a particular FTUE step drove retention. |

Read the decision-oriented interpretation and recommendations in the
[stakeholder brief](docs/stakeholder_brief.md).

## Deliverables

| Deliverable | Location |
| --- | --- |
| Product findings and recommendations | [`docs/stakeholder_brief.md`](docs/stakeholder_brief.md) |
| Scalable AWS data architecture proposal | [`docs/architecture_proposal.md`](docs/architecture_proposal.md) |
| Portable Superset dashboard bundle | [`outputs/superset_dashboard.zip`](outputs/superset_dashboard.zip) |
| Independent aggregate reconciliation | [`outputs/metric_reconciliation.json`](outputs/metric_reconciliation.json) |

## Technology choices

- **Python 3.12** validates source structure and performs idempotent ingestion.
- **DuckDB** keeps the assignment self-contained and inexpensive to run.
- **dbt Core + dbt-duckdb** define transformations, contracts, tests, governed
  metrics, lineage, and dashboard exposures.
- **Apache Superset 6** serves the loading and FTUE dashboards from Docker.
- **uv** installs the exact Python environment recorded in `uv.lock`.

No cloud account, external database, or API credentials are required.

## Quick start: reproduce the analysis

### Prerequisites

- [uv](https://docs.astral.sh/uv/)
- Python 3.12, which `uv` can install automatically when needed
- Docker Desktop with Docker Compose, only for the interactive dashboards
- The supplied `events.jsonl`, `funnel_steps.csv`, and `installs.csv` files in
  the repository root

Run all commands from the repository root.

> **Data note:** `events.jsonl` and `installs.csv` contain user-level assignment
> data and are intentionally excluded from source control. Obtain the original
> files through the assessment package and place them in the repository root.
> The non-user-level `funnel_steps.csv` configuration is included in the repo.

### 1. Install the locked environment

```bash
uv sync --locked
```

This creates an isolated `.venv` and installs the exact dependency versions in
`uv.lock`. The `--locked` option prevents an unnoticed dependency upgrade from
changing the results.

### 2. Run the automated tests

```bash
uv run pytest -q
```

These tests cover source parsing, idempotent ingestion, joins, funnel ordering,
deduplication, FTUE calculations, dashboard layout, and export integrity. The
current suite contains 24 tests.

### 3. Build the analytical database

```bash
uv run game-analytics build --database data/superset_analytics.duckdb
```

This is the main reproducible entry point. It performs two operations:

1. validates and ingests the three raw inputs in **quarantine mode**, preserving
   rejected-row metadata without exposing rejected payloads; and
2. runs `dbt build`, which creates the staging, intermediate, fact, dimension,
   quality, and dashboard-mart models and executes their tests.

The supplied telemetry intentionally contains three malformed JSONL rows. A
successful build accepts 18,476 structurally valid event rows and quarantines
three malformed rows. Downstream metrics use 18,400 rows after also excluding
70 later exact-duplicate copies and six out-of-window events.

The expected dbt result has no errors. One warning is intentional: it summarizes
known data-quality findings that remain visible for investigation rather than
being silently removed.

### 4. Reconcile the published metrics independently

```bash
uv run python src/reconcile_metrics.py
```

This script reads the supplied files directly instead of querying the dbt marts.
It recalculates the headline, funnel, conditional-outcome, segment, and FTUE
metrics through a second implementation and writes aggregate-only results to
`outputs/metric_reconciliation.json`. This guards against validating dbt logic
with another query that repeats the same assumptions.

At this point the analysis, tests, dbt models, and reconciliation artifact are
complete. Docker is only needed if you want to use the interactive dashboards.

## Launch the Superset dashboards

### 1. Configure local credentials

If `superset/.env` does not already exist, copy the template:

```bash
cp superset/.env.example superset/.env
```

Edit `superset/.env` and replace the example secret and password. These values
are local-only and the file is ignored by Git.

### 2. Start Superset

```bash
docker compose up -d --build --wait
```

Docker builds the repository-local Superset image, upgrades its metadata
database, creates the local administrator when necessary, and waits until the
web service reports healthy. Superset metadata persists in a named Docker
volume, so stopping the container does not remove saved dashboards.

### 3. Create or update the dashboard objects

```bash
uv run python src/configure_superset.py
```

The idempotent configurator registers the DuckDB database as read-only, refreshes
five datasets, creates or updates 12 charts and two dashboards, applies their
shared visual theme, and regenerates `outputs/superset_dashboard.zip`. Rerun it
after changing dashboard definitions or rebuilding the Superset metadata store.

Open the dashboards and sign in with the credentials from `superset/.env`:

- [Launch Health · Loading](http://localhost:8088/superset/dashboard/technical-launch-loading-funnel/)
- [Launch Health · FTUE](http://localhost:8088/superset/dashboard/technical-launch-ftue/)
- [Superset home](http://localhost:8088/)

The loading dashboard presents the executive KPIs, mandatory ten-step journey,
drop-offs, conditional outcomes, and platform/version diagnostics. The FTUE
dashboard uses the same typography, color system, structure, and terminology
for first-session entry, activation, time to value, and D1 retention.

### Stop or inspect Superset

```bash
# Confirm whether the service is healthy.
docker compose ps

# Inspect startup or runtime errors.
docker compose logs superset

# Stop the service while retaining its metadata volume.
docker compose stop
```

## Explore dbt documentation and lineage

dbt Docs does not require Docker. Generate the catalog against the same DuckDB
database used by Superset, then serve the static documentation on port 8081:

```bash
# Build catalog.json, manifest.json, and the documentation site.
uv run dbt docs generate \
  --project-dir dbt \
  --profiles-dir dbt \
  --vars "{analytics_database: 'data/superset_analytics.duckdb'}"

# Keep this process running while browsing the documentation.
uv run dbt docs serve \
  --project-dir dbt \
  --profiles-dir dbt \
  --port 8081
```

Open [dbt Docs](http://localhost:8081), select a model, and use the graph control
to expand its upstream and downstream lineage. The two Superset dashboards are
declared as dbt exposures named `technical_launch_loading_funnel` and
`technical_launch_ftue`, so the graph continues through the end-consumer
boundary.

Run `dbt docs generate` again after changing models, descriptions, tests,
metrics, or exposures. Port 8081 is intentionally separate from Superset's
default port 8088.

## How the analytical pipeline works

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

Important design decisions:

- Raw input files are never modified.
- Source batches are content-addressed and ingestion is idempotent.
- User identifiers and timestamps are normalized before joins or metric logic.
- Required funnel steps are evaluated sequentially within a user session.
- Optional or conditional outcomes use their own denominators rather than being
  represented as mandatory funnel stages.
- Governed metric logic lives in dbt, not in dashboard-specific SQL.
- Final outputs contain aggregates rather than unnecessary raw user identifiers.

### Governed dashboard marts

| Model | Purpose |
| --- | --- |
| `analytics.mart_launch_summary` | Overall loading completion and duration KPIs |
| `analytics.mart_primary_funnel` | Ordered step counts, conversion, and drop-off |
| `analytics.mart_branch_outcomes` | Continuation after conditional decisions or failures |
| `analytics.mart_segment_performance` | Platform and client-version comparisons |
| `analytics.mart_ftue_summary` | First-session entry, activation, time to battle, and mature-cohort D1 retention |

`funnel_steps.csv` remains the product-owned ordering of the primary journey.
The analytics-owned semantics in `dbt/seeds/funnel_event_semantics.csv` identify
which events are milestones, starts, ends, outcomes, failures, platform-specific
branches, or post-entry diagnostics.

## Metric definitions and boundaries

- **Primary funnel:** session attempts beginning with `INIT_CLIENT_START` and
  ending with `INIT_GAME_JOINED`. Each required event must occur at or after the
  preceding step in the same session.
- **Loading time:** elapsed time from client start to game joined. Twenty-one
  completed sessions with incoherent source timestamp order are excluded from
  duration statistics, leaving 556 timing-eligible sessions.
- **Conditional outcome continuation:** affected sessions with a later
  `INIT_GAME_JOINED` event in the same session divided by all sessions observing
  that outcome. Privacy decline and iOS tracking denial are therefore not
  treated as loading abandonment when the session continues.
- **First-session activation:** a `BATTLE_STARTED` event after sequential game
  entry in the player's first eligible session.
- **D1 retention:** mature installs with an eligible `INIT_CLIENT_START` on the
  exact next UTC calendar day. Installs whose next day is not fully observable
  are excluded.

Tutorial completion, battle retries, progression state, authoritative session
duration, and crash-free onboarding are not reported because the required
events or fields are absent. D3 and D7 are deferred because the 14-day snapshot
would leave smaller, unstable mature cohorts.

## Additional validation commands

These commands are useful for investigation but are not required for the normal
quick-start path:

```bash
# Demonstrate fail-fast behavior. This is expected to return a non-zero status
# because events.jsonl contains three malformed rows.
uv run game-analytics ingest --mode strict

# Validate the resolved Docker Compose configuration without starting services.
docker compose config

# Optional independent SQL check when the DuckDB CLI is installed.
duckdb data/superset_analytics.duckdb < sql/reconcile_ftue_kpis.sql
```

To restore the portable dashboard bundle into an otherwise empty Superset
metadata store instead of running the Python configurator:

```bash
docker compose cp outputs/superset_dashboard.zip superset:/tmp/superset_dashboard.zip
docker compose exec superset sh -lc \
  'superset import-dashboards --path /tmp/superset_dashboard.zip --username "$SUPERSET_ADMIN_USERNAME"'
```

Choose either the source-controlled configurator or the import workflow for a
fresh instance; running both creation paths is unnecessary.

## Troubleshooting

### Superset does not become healthy

Run `docker compose ps` followed by `docker compose logs superset`. Confirm that
Docker Desktop is running and that port 8088 is not already in use.

To use another port:

```bash
SUPERSET_PORT=18088 docker compose up -d --build --wait
SUPERSET_URL=http://localhost:18088 uv run python src/configure_superset.py
```

### dbt cannot find the database

Run the main `game-analytics build` command first and confirm that
`data/superset_analytics.duckdb` exists. Keep the `--vars` database path on the
`dbt docs generate` command so documentation is generated from the intended
database.

### Results appear stale after a change

Rebuild the DuckDB database, rerun `src/reconcile_metrics.py`, and then rerun
`src/configure_superset.py`. Regenerate dbt Docs separately if model metadata or
lineage changed.

## Project structure

```text
.
├── brief.md                    Assignment requirements
├── events.jsonl                Raw client telemetry
├── installs.csv                Install and attribution data
├── funnel_steps.csv            Product-owned loading sequence
├── src/game_analytics/         Validation, ingestion, and CLI
├── src/configure_superset.py   Dashboard-as-code configurator
├── src/reconcile_metrics.py    Independent metric implementation
├── dbt/                        Models, tests, metrics, seeds, and exposures
├── sql/                        Direct SQL reconciliation
├── tests/                      Python behavior and metric tests
├── superset/                   Local Superset image and configuration
├── outputs/                    Aggregate and portable dashboard artifacts
└── docs/                       Stakeholder brief and architecture proposal
```

User-level source data, generated databases, rejected raw payloads, caches,
local credentials, dbt build artifacts, and local workspace instructions are
excluded through `.gitignore`.

## AI assistance and independent verification

AI assistance was used to accelerate source profiling, implementation drafts,
test design, dashboard configuration, documentation editing, and architecture
review. I worked largely through plan-driven iterations: drafting and revising
the approach, incorporating system-design considerations, consulting specialist
agents, and then implementing the agreed plan. Generated suggestions were
treated as proposals rather than evidence and as starting points for discussion
and critical review.

I manually reviewed the source files and representative records to develop a
working understanding of the domain and how the datasets fit together. My
preferred workflow is to ingest data as supplied, identify quality issues, and
then clean and transform only what is necessary to support the analysis.

At each major milestone, I reviewed the proposed reasoning and challenged points
that did not make sense. I asked for alternative validation where appropriate
and inspected tangible outputs—including analyses, tests, and dashboard
charts—rather than accepting generated responses at face value. I also prompted
the AI to critique both my feedback and its own conclusions, ask questions when
context was unclear, and avoid claims unsupported by the supplied or verified
information.

The results were independently verified through:

- Python tests for ingestion behavior and metric edge cases;
- dbt contracts, unit tests, relationship tests, and custom business assertions;
- a raw-file Pandas reconciliation implemented separately from dbt;
- a direct SQL cross-check for FTUE numerators and timing statistics; and
- live execution of all 12 Superset chart queries against the governed marts.

The definition of the mandatory loading funnel—and the decision to keep patch,
privacy, and Apple tracking outcomes on conditional denominators—was deliberately
retained as an analyst-owned product judgment. Event order alone cannot determine
whether a prompt is universally required, platform-specific, recoverable, or
post-entry; automating that choice would risk producing a visually plausible but
conceptually incorrect funnel.

## Part 2: architecture proposal

Part 2 is intentionally a design document rather than an implementation. It
proposes a low-cost AWS serverless data lake for pre-launch, separates governed
reporting from exploratory analytics, provides a distinct 15–20 minute payments
path, and identifies measured triggers for adopting Glue Spark, Iceberg, or
Redshift Serverless as volume approaches 1 TB/day.

See [`docs/architecture_proposal.md`](docs/architecture_proposal.md) for the
end-to-end diagram, governance model, quality controls, concurrency strategy,
cost drivers, and deliberately deferred scope.
