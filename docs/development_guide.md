# Development and Diagnostic Guide

## Purpose

The README contains the standard setup and reproduction path. This guide holds
optional developer workflows for inspecting lineage, running extra checks, and
restoring the portable Superset dashboard bundle.

Run all commands from the repository root after completing the README build.

## Explore dbt documentation and lineage

dbt Docs does not require Docker. Generate its catalog against the DuckDB
database used by Superset:

```bash
uv run dbt docs generate \
  --project-dir dbt \
  --profiles-dir dbt \
  --vars "{analytics_database: 'data/superset_analytics.duckdb'}"
```

Serve the generated site on port 8081:

```bash
uv run dbt docs serve \
  --project-dir dbt \
  --profiles-dir dbt \
  --port 8081
```

Open [dbt Docs](http://localhost:8081), select a model, and use the graph control
to expand upstream and downstream lineage. The Superset dashboards are declared
as dbt exposures named `technical_launch_loading_funnel` and
`technical_launch_ftue`, so lineage continues through the consumer boundary.

Regenerate the documentation after changing models, descriptions, tests,
metrics, or exposures. Port 8081 is separate from Superset's default port 8088.

## Additional validation commands

These checks are not required for the normal reproduction path:

```bash
# Demonstrate fail-fast behavior. A non-zero result is expected because the
# supplied events.jsonl contains three malformed rows.
uv run game-analytics ingest --mode strict

# Validate the resolved Compose configuration without starting services.
docker compose config

# Run an independent SQL check when the DuckDB CLI is installed.
duckdb data/superset_analytics.duckdb < sql/reconcile_ftue_kpis.sql
```

## Restore the portable dashboards

For a fresh Superset metadata store, the normal and preferred path is the
source-controlled configurator documented in the README. To test the exported
bundle instead, run:

```bash
docker compose cp outputs/superset_dashboard.zip superset:/tmp/superset_dashboard.zip
docker compose exec superset sh -lc \
  'superset import-dashboards --path /tmp/superset_dashboard.zip --username "$SUPERSET_ADMIN_USERNAME"'
```

Choose either the configurator or import workflow when creating a fresh
instance. Running both creation paths is unnecessary.
