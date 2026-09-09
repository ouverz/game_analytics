# End-to-End Pipeline Monitoring and Data Quality

## Purpose

This document defines how the proposed AWS data platform should determine
whether data moved successfully from its source to a stakeholder-facing
dashboard. It is the operational companion to the
[architecture proposal](architecture_proposal.md).

The central principle is that **a successful task is not the same as a
successful pipeline**. Python can exit successfully even though an expected file
never arrived. dbt can pass while reading an incomplete partition. A dashboard
can remain stale after every upstream job completes. Monitoring must therefore
follow a shared run from expected source arrival through final publication.

## Definition of success

A daily reporting run is successful only when:

1. every required source partition arrived within its agreed grace period;
2. each file passed structural validation or was handled under an approved
   quarantine threshold;
3. input, accepted, rejected, duplicate, and output counts reconcile;
4. curated data was written idempotently and registered in the catalog;
5. blocking dbt tests passed against the intended input version;
6. certified views were promoted without exposing a partial result;
7. Quick Sight refreshed successfully; and
8. a consumer-level check confirmed the expected `data_as_of` watermark and
   headline totals.

The live-payment path is successful when the newest valid Payment Hub delivery
is visible in the provisional dashboard within 15–20 minutes. Its daily
reconciliation remains a separate certification requirement.

```text
Expected source
      ↓
S3 arrival and manifest validation
      ↓
Python decode, validation, normalization and quarantine
      ↓
Curated Parquet publication and Glue registration
      ↓
dbt build, reconciliation and quality gates
      ↓
Certified-view promotion
      ↓
Quick Sight refresh or live-payment watermark
      ↓
End-to-end freshness and canary checks
```

## Shared run identity and control record

Step Functions acts as the control plane. Every execution receives a `run_id`,
which is passed to Python, dbt, manifests, logs, alerts, and publication checks.
A DynamoDB run ledger stores one control record per source partition and a
parent record for the complete reporting run.

Recommended fields include:

| Field group | Examples |
| --- | --- |
| Identity | `run_id`, environment, pipeline, source, partition |
| Input | expected objects, received objects, checksums, source schema version |
| Processing | code version, started/completed timestamps, task status |
| Reconciliation | physical, decoded, accepted, rejected, duplicate, and output counts |
| Quality | issue counts/rates, threshold result, quarantine location |
| Transformation | dbt invocation ID, models built, tests passed/warned/failed |
| Publication | certified dataset version, Quick Sight refresh ID, `data_as_of` |
| Operations | status, owner, failure code, retry count, runbook link |

Suggested run states are:

```text
EXPECTED → RECEIVED → VALIDATED → CURATED → DBT_PASSED
         → CERTIFIED → SERVING_REFRESHED → PUBLISHED

Any stage may become WARNING, FAILED, QUARANTINED or STALE.
```

The ledger answers the operational question: “Did partition X reach its
consumers, and where did it stop?” It also prevents an unchanged source from
being processed twice and connects a dashboard result back to source objects,
schema, and code versions.

## Monitoring source arrival

An event-driven process cannot detect an object that never arrived. Each source
therefore needs an explicit delivery contract and a scheduled completeness
check.

| Source | Expected delivery | Example response |
| --- | --- | --- |
| Gameplay wire log | Hourly S3 partitions | Warn after the grace period; page if backlog threatens the daily reporting SLO |
| Payment Hub live | Every 15 minutes | Alert when the next expected watermark is late |
| Payment Hub daily | Once daily | Block certified revenue until the authoritative partition is complete |
| AppsFlyer | Daily | Block attribution-dependent marts or retain last-good data |
| Firebase export | Daily | Warn or block according to which certified metrics depend on it |

S3 object-created events start processing when data arrives. EventBridge also
runs a watchdog after each delivery deadline. The watchdog compares the
expected manifest with S3 and the run ledger, detecting:

- missing, late, empty, or unexpectedly small/large files;
- duplicate object delivery;
- checksum changes to a previously processed object;
- unexpected partition paths or file formats; and
- incomplete multi-file deliveries.

The manifest should be treated as part of the source contract whenever the
provider can supply one. Otherwise the platform creates its own arrival
manifest before transformation begins.

## Source-to-Python data-quality controls

Python must emit a machine-readable validation report for every source
partition. Free-form logs are useful for diagnosis but are not sufficient for
gating or reconciliation.

### Structural controls

These establish whether records can be interpreted safely:

- file exists, is non-empty, and uses the expected encoding/compression;
- CSV headers and row widths match the versioned contract;
- Protocol Buffer schema/version is known and decoding succeeds;
- JSON values are syntactically valid and have the expected shape;
- required envelope fields are present; and
- file and record checksums can be calculated.

An unreadable file, incompatible header, or unknown Protobuf version blocks the
partition because record boundaries or meaning cannot be trusted. Isolated
malformed records can be quarantined if the reject rate remains within an
approved threshold.

### Semantic and consistency controls

Records that are structurally readable are then checked for:

- identifier, timestamp, Boolean, numeric, amount, and currency validity;
- timestamps outside the expected window or decreasing within a session;
- exact duplicates and natural-key collisions;
- missing required versus optional values;
- unexpected event names or category values;
- invalid platform-specific events;
- install/event attribution conflicts and missing reference joins; and
- payment transaction versions, refund links, and booking relationships.

Raw values remain immutable. Safe normalization—such as canonical UTC
timestamps, platform labels, and identifiers—occurs beside the raw value and is
recorded in the quality output. The pipeline must not silently invent corrected
dates, identifiers, amounts, or categories.

### Quarantine and reconciliation

Rejected records go to an encrypted, access-restricted S3 quarantine prefix
containing source, partition, record location, issue code, raw hash, schema
version, and `run_id`. Retention and access should be stricter than for
aggregated analytical data because rejected payloads may contain identifiers or
other sensitive values.

Every run must balance:

```text
physical source records
= structurally accepted records
+ structurally rejected records

structurally accepted records
= curated records
+ exact duplicate copies
+ records excluded by another explicitly reported rule
```

Any unexplained difference is a blocking failure.

### Validation report example

```json
{
  "run_id": "2026-09-09-gameplay-14",
  "source": "wire_log",
  "partition": "2026-09-09/14",
  "source_rows": 1000000,
  "decoded_rows": 999920,
  "quarantined_rows": 80,
  "duplicate_rows": 1200,
  "curated_rows": 998720,
  "unknown_schema_rows": 0,
  "status": "warning"
}
```

## Issue severity and publication decisions

Thresholds should combine an absolute count, a percentage, and comparison with
recent history. Eighty rejects may be immaterial in ten million records but
critical in a file containing one hundred records. A new issue type can also be
important even when its count is low.

| Condition | Default response |
| --- | --- |
| Missing/unreadable required file | Fail; retain last certified version |
| Unknown or incompatible schema | Fail; quarantine partition and notify source owner |
| Small, understood malformed-record rate | Quarantine rows; publish with warning |
| Reject rate over threshold or sharply above baseline | Block promotion and page owner |
| Missing optional field | Publish; record and trend the issue |
| Missing/unparseable required field | Quarantine row; block when threshold is breached |
| Duplicate delivery or exact duplicate record | Deduplicate idempotently; report count |
| Natural-key collision with different payload | Quarantine or block pending ownership rule |
| Unexplained volume movement | Warn or block according to source criticality |
| Payment control-total mismatch | Block certified revenue |

Warnings are appropriate only when the affected metric remains valid. A
timestamp-order problem, for example, may invalidate duration without
invalidating a funnel count. Eligibility should therefore be metric-specific
rather than based on one global “clean record” flag.

## Structured telemetry from Python

Python should log JSON with stable fields such as `run_id`, source, partition,
stage, status, issue code, counts, duration, and code/schema version. It should
also publish bounded-dimension CloudWatch metrics:

- `FilesExpected`, `FilesReceived`, and `FilesLate`;
- `SourceRows`, `AcceptedRows`, `QuarantinedRows`, and `RejectRate`;
- `DuplicateRate`, `UnknownSchemaCount`, and `RequiredFieldFailureRate`;
- `TransformationDuration` and `TransformationFailures`;
- `PartitionBacklog` and `OldestUnprocessedPartitionAge`; and
- `InputOutputReconciliationDifference`.

Useful metric dimensions are environment, pipeline, source, stage, and issue
code. User IDs, transaction IDs, file names, and other high-cardinality or
sensitive values belong in restricted logs, not metric dimensions.

At higher volume, Glue Spark and Glue Data Quality/Deequ may replace the
single-task implementation. The validation report, metrics, thresholds, and run
ledger contract should remain stable so observability does not change when
compute changes.

## Connecting ingestion quality to dbt

dbt should consume the ingestion manifest/run ledger as a declared source. This
allows tests to prove that dbt received the intended data, not merely that its
SQL returned internally consistent tables.

Recommended cross-boundary tests include:

- every curated partition has a successful ingestion record;
- curated counts reconcile to Python's accepted counts;
- only one source batch/version is promoted;
- no partition with a blocking validation result enters certified models;
- source freshness agrees with the expected ingestion watermark;
- maximum event timestamps agree across manifest, curated data, and marts; and
- payment facts reconcile to the provider's authoritative control totals.

Store dbt `manifest.json`, `run_results.json`, test summaries, and the deployed
model version against the same `run_id`. dbt tests then cover model grain,
relationships, accepted values, business logic, and reconciliation, while the
run ledger closes the gap between ingestion and transformation.

## Serving-layer checks

The pipeline is not complete when dbt finishes. After successful tests:

1. advance certified views to the new version;
2. trigger the Quick Sight SPICE refresh;
3. poll until the refresh succeeds or times out;
4. query each critical mart through the consumer-facing endpoint;
5. verify `data_as_of`, row availability, and selected headline totals; and
6. mark the run `PUBLISHED` only after these checks pass.

The canary should use governed consumer views rather than underlying tables so
it catches broken permissions, view promotion, catalog changes, and serving
failures. For live payments, the equivalent canary confirms that the latest
Payment Hub event and ingestion watermarks are visible within the 15–20 minute
SLO.

## Alerts, successful-run notifications, and ownership

Not every signal should wake an engineer. Notifications are routed by impact:

| Level | Delivery | Example |
| --- | --- | --- |
| Success | Daily Slack/Teams digest and monitoring dashboard | All sources received, publication time, freshness, quality rates, dbt result, and dashboard link |
| Warning | Team channel and ticket | Optional-field drift, elevated but permitted rejects, or a recoverable delay within the SLO |
| Failure | Owning team and incident channel | Partition blocked, dbt promotion failed, or SPICE refresh failed |
| Page | PagerDuty/on-call | Certified reporting or payment freshness SLO is breached or at imminent risk |
| Recovery | Original channel/incident | Replay succeeded, watermark recovered, and certified data is current |

Example success notification:

> Daily analytics published for 2026-09-08 at 06:42 UTC. All four sources were
> received; 99.98% of records were accepted; blocking dbt tests passed; Quick
> Sight refreshed; `data_as_of` is 2026-09-08 23:59 UTC.

Example actionable failure:

> Payment data is 27 minutes stale. Expected partition `10:15` was not received.
> Last visible watermark: `10:00`. Owner: Payments Data. Runbook: PAY-01.

Every alert should include environment, affected source/partition, current and
expected watermark, `run_id`, failure stage/code, severity, owner, dashboard,
and runbook. Success messages should be summarized rather than emitted for every
task to avoid alert fatigue.

## Recovery and replay

The runbook for a failed partition should be predictable:

1. identify the failing stage through the parent `run_id`;
2. confirm whether the problem is missing input, source quality, code, schema,
   infrastructure, or serving refresh;
3. keep the last certified version available with a staleness banner;
4. correct the source contract or transformation without modifying raw data;
5. replay the same source/date partition through the idempotent workflow;
6. rerun Python reconciliation, dbt gates, promotion, and serving canaries; and
7. send recovery notification and record the incident outcome.

Retries should be automatic only for transient infrastructure failures. Data
contract failures should not retry indefinitely because repeating the same bad
input creates noise without changing the outcome.

## Minimum initial implementation

The initial platform does not need a separate observability vendor. A practical
first version consists of:

- Step Functions for state and retries;
- EventBridge for arrivals, deadlines, and scheduled watchdogs;
- DynamoDB for the run/idempotency ledger;
- structured Python validation reports in S3 and CloudWatch Logs;
- CloudWatch metrics, dashboards, and alarms;
- SNS with Slack/Teams and PagerDuty routing;
- dbt artifacts and cross-boundary reconciliation tests; and
- post-publication Quick Sight/payment canaries.

The key investment is the shared run contract and consumer-facing freshness
check. Additional tooling can improve the interface later, but it should not
replace these controls or create a second definition of pipeline health.
