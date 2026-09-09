# Annex: Production Ingestion and Validation Considerations

## Status and scope boundary

This annex is an optional design reference, not an implemented Part 1
deliverable. The assignment states that wire logs, Payment Hub, and AppsFlyer
data already land in Amazon S3 and that Firebase is available through export.
Producer-to-S3 delivery is therefore outside the required design boundary.

The notes below show how the local preparation lessons could inform production
acceptance after objects arrive in S3. They supplement, but do not expand the
committed scope of, the [architecture proposal](architecture_proposal.md). The
broader monitoring model is documented in
[pipeline_monitoring.md](pipeline_monitoring.md).

## Ownership and responsibility

**Source teams own data correctness; the data platform owns contract enforcement
and safe processing; analytics owns fitness for analytical use.** Detecting and
containing a source defect does not transfer accountability for correcting it to
the data team. The platform should preserve evidence, prevent unsafe publication,
and support replay rather than silently inventing or repairing source semantics.

| Concern or issue | Accountable owner | Platform/data-team responsibility |
| --- | --- | --- |
| Schema and Protobuf version | Source owner defines, versions, and publishes the contract | Validate the declared version; reject unsupported data |
| Required fields and valid values | Source owner produces contract-compliant records | Detect violations and prevent unsafe publication |
| File completeness and timeliness | Source/export owner supplies finalized files, manifests, counts, and control totals | Verify arrival, checksum, size, counts, and freshness |
| Event and transaction identifiers | Source owner generates stable identifiers | Enforce idempotency and monitor duplicates defensively |
| Timestamp and event semantics | Source owner defines meaning, timezone, and valid states | Normalize only by agreed rules; flag ambiguity or violations |
| Malformed or semantically invalid data | Source owner corrects the producer and resupplies/backfills | Quarantine, alert, retain lineage, and replay corrected delivery |
| Analytical grain, joins, and eligibility | Analytics/data team | Define facts, dimensions, exclusions, and fitness-for-use tests |
| KPI definitions and dashboard logic | Analytics/data team with business owners | Govern definitions in dbt and verify published outputs |
| Safe publication and recovery | Data platform | Block failed versions, retain last-good data, expose freshness, and operate replay |

Contracts, thresholds, backward-compatibility rules, and incident routes should
be agreed jointly. The source owner remains accountable for remediation; the
platform owner is accountable for ensuring a violation cannot silently
contaminate governed outputs.

## Considered production flow

```text
Source-owned delivery
        |
S3 immutable landing object
        |
EventBridge -> Step Functions run
        |
manifest and file acceptance checks
        |
parallel decode + structural validation
       / \
      /   \ invalid record + reason
     v     v
curated   restricted quarantine
data          |
  |       alert / investigation
semantic and reconciliation checks
        |
promote partition or retain last-good version
```

## Landing contract

Every delivery should use a predictable `source/date/hour` prefix and provide,
or allow the platform to calculate:

- object key, byte size, modification time, and checksum;
- expected delivery interval and lateness tolerance;
- schema or Protobuf descriptor version;
- source-side record count and financial control totals where available; and
- a correlation identifier carried into the processing run.

S3 versioning, KMS encryption, lifecycle rules, and restricted IAM/Lake
Formation policies protect the original objects. Landing files remain immutable
so a corrected transformation can be replayed without asking the producer to
resend history.

The platform should not infer that an S3 object is complete merely because it
exists. Multipart uploads or source-side temporary objects should be finalized
through an agreed naming/manifest convention before processing begins.

## Acceptance and validation layers

### 1. Delivery checks

Before reading records, validate that the expected source arrived on time, is
non-empty, has not already been processed under the same checksum, and agrees
with its manifest. Missing, late, empty, unexpectedly large, or duplicate files
produce an explicit run state rather than silently appearing as zero activity.

### 2. Structural checks

The decoder or parser should verify:

- readable encoding and compression;
- expected CSV header and row width, or object-shaped JSON;
- recognized Protobuf descriptor version;
- parseable required fields and supported primitive types; and
- a reason code plus source location for each rejected record.

A file-level schema failure blocks the partition because record interpretation
is unsafe. An isolated malformed record can be quarantined when the source
contract permits partial acceptance and the reject rate remains below an agreed
threshold.

### 3. Semantic checks

Structurally valid data still requires checks for event identity, timestamp
range, duplicate rate, platform applicability, session consistency, reference
joins, and volume drift. Payment data additionally requires valid amount and
currency, unique transaction versions, linked refunds/bookings, and agreement
with provider control totals.

### 4. Cross-layer reconciliation

Each run should reconcile counts across landed, accepted, rejected, deduplicated,
curated, and published records:

```text
landed = structurally accepted + structurally rejected
accepted = curated first copies + excluded duplicates
published facts = eligible curated facts after documented semantic exclusions
```

The run record should retain source checksum, row counts, reject counts, code and
schema versions, dbt invocation, published version or Iceberg snapshot, and a
shared `run_id`.

## Publication policy

Validation outcomes should have predetermined consequences:

| Outcome | Example | Action |
| --- | --- | --- |
| Pass | Expected file and reconciliation totals | Publish and notify success |
| Warn | Small optional-field drift below threshold | Publish with visible warning |
| Quarantine | Isolated malformed records below threshold | Publish accepted rows and restrict rejects |
| Fail | Unknown schema, missing required file, or broken control totals | Do not promote; retain last-good data |
| Stale | Delivery misses its freshness objective | Display stale watermark and alert owner |

Thresholds should be agreed per source and based on normal history rather than
invented globally. A warning becomes blocking only when it violates a consumer
contract, threatens metric correctness, or exceeds the source's documented
tolerance.

## How the assignment findings inform production controls

| Observed assignment issue | Candidate production control |
| --- | --- |
| Three malformed JSON lines | Parser rejection count and restricted quarantine |
| Mixed timestamp representations | Explicit timestamp contract and coercion-rate metric |
| Exact duplicate payloads | Producer event ID plus checksum/natural-key duplicate monitoring |
| Future-dated telemetry | Event-time versus receive-time threshold |
| Pre-install events | Install-source reconciliation and chronology alert |
| Session timestamp reversals | Sequence-consistency metric; exclude only duration calculations |
| Platform-inapplicable events | Platform/event compatibility test |
| Missing attribution | Join-coverage SLO without dropping valid gameplay events |

## Alert and recovery expectations

CloudWatch metrics and structured logs should report arrival delay, accepted and
rejected counts, reject rate, duplicate rate, processing duration, backlog,
reconciliation difference, and publication freshness. Alerts should include the
source, partition, `run_id`, severity, owner, and runbook link. Success and
recovery notifications are also useful so downstream users know when data is
safe again.

Replay should accept an explicit source and partition, reuse the immutable
landing object, create a new run record, and publish only after the same quality
gates pass. No repair should require editing the original S3 object.

## Deliberately deferred

For this assignment, it was reasonable not to implement S3 delivery contracts,
AWS orchestration, production alert routing, automated schema-registry approval,
or multi-environment deployment. The supplied files and local DuckDB pipeline
were sufficient to demonstrate parsing, preparation, quarantine behavior,
testing, and metric correctness. This annex records how those ideas could evolve
without presenting optional infrastructure as completed work.
