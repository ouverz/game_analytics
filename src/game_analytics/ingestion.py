"""Structural validation and idempotent DuckDB ingestion."""

from __future__ import annotations

import csv
import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import duckdb

Mode = Literal["strict", "quarantine"]

EXPECTED_HEADERS = {
    "installs.csv": [
        "user_id",
        "install_date",
        "platform",
        "install_source",
        "country",
    ],
    "funnel_steps.csv": ["step_order", "event_name"],
}


@dataclass(frozen=True)
class RejectedRecord:
    source_file: str
    source_line: int | None
    rejection_code: str
    rejection_message: str
    raw_text: str | None


@dataclass
class ValidatedSources:
    hashes: dict[str, str]
    batch_id: str
    events: list[tuple[int, str, str]] = field(default_factory=list)
    installs: list[tuple[int, list[str], str]] = field(default_factory=list)
    funnel_steps: list[tuple[int, list[str], str]] = field(default_factory=list)
    rejects: list[RejectedRecord] = field(default_factory=list)
    physical_counts: dict[str, int] = field(default_factory=dict)
    unusable_files: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class IngestionResult:
    execution_id: str
    batch_id: str
    status: str
    promoted: bool
    counts: dict[str, int]
    reject_lines: dict[str, list[int]]
    failure_summary: str | None = None

    @property
    def exit_code(self) -> int:
        return 0 if self.status in {"promoted", "already_promoted"} else 1


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _raw_hash(raw_text: str) -> str:
    return _sha256_bytes(raw_text.encode("utf-8"))


def _read_utf8(path: Path) -> tuple[bytes | None, str | None]:
    try:
        content = path.read_bytes()
    except OSError as exc:
        return None, f"unreadable file: {exc}"
    if not content:
        return None, "file is empty"
    try:
        content.decode("utf-8")
    except UnicodeDecodeError as exc:
        return None, f"file is not valid UTF-8: {exc}"
    return content, None


def _validate_jsonl(content: bytes, result: ValidatedSources) -> None:
    text = content.decode("utf-8")
    lines = text.splitlines()
    # A terminal newline is not an additional physical line.
    result.physical_counts["events.jsonl"] = len(lines)
    for line_number, raw_line in enumerate(lines, start=1):
        if not raw_line.strip():
            result.rejects.append(
                RejectedRecord(
                    "events.jsonl",
                    line_number,
                    "blank_line",
                    "JSONL line is blank",
                    raw_line,
                )
            )
            continue
        try:
            payload = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            result.rejects.append(
                RejectedRecord(
                    "events.jsonl",
                    line_number,
                    "invalid_json",
                    f"{exc.msg} at column {exc.colno}",
                    raw_line,
                )
            )
            continue
        if not isinstance(payload, dict):
            result.rejects.append(
                RejectedRecord(
                    "events.jsonl",
                    line_number,
                    "non_object_json",
                    "JSONL value must be an object",
                    raw_line,
                )
            )
            continue
        canonical_payload = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        result.events.append((line_number, canonical_payload, _raw_hash(raw_line)))


def _validate_csv(
    filename: str,
    content: bytes,
    result: ValidatedSources,
) -> None:
    text = content.decode("utf-8")
    physical_lines = text.splitlines()
    result.physical_counts[filename] = len(physical_lines)
    try:
        rows = list(csv.reader(physical_lines, strict=True))
    except csv.Error as exc:
        result.unusable_files.append(filename)
        result.rejects.append(
            RejectedRecord(filename, None, "unreadable_csv", str(exc), None)
        )
        return

    expected = EXPECTED_HEADERS[filename]
    if not rows or rows[0] != expected:
        result.unusable_files.append(filename)
        observed = rows[0] if rows else []
        result.rejects.append(
            RejectedRecord(
                filename,
                1 if rows else None,
                "incorrect_headers",
                f"expected {expected!r}; observed {observed!r}",
                physical_lines[0] if physical_lines else None,
            )
        )
        return

    destination = result.installs if filename == "installs.csv" else result.funnel_steps
    for source_line, row in enumerate(rows[1:], start=2):
        raw_text = physical_lines[source_line - 1] if source_line <= len(physical_lines) else None
        if len(row) != len(expected):
            result.rejects.append(
                RejectedRecord(
                    filename,
                    source_line,
                    "incorrect_field_count",
                    f"expected {len(expected)} fields; observed {len(row)}",
                    raw_text,
                )
            )
            continue
        destination.append((source_line, row, _raw_hash(raw_text or "")))


def validate_sources(source_dir: Path) -> ValidatedSources:
    """Validate source structure without applying analytical type rules."""
    contents: dict[str, bytes] = {}
    hashes: dict[str, str] = {}
    read_errors: dict[str, str] = {}
    for filename in ("events.jsonl", "installs.csv", "funnel_steps.csv"):
        content, error = _read_utf8(source_dir / filename)
        if error:
            read_errors[filename] = error
            hashes[filename] = _sha256_bytes(f"UNREADABLE:{filename}:{error}".encode())
        else:
            assert content is not None
            contents[filename] = content
            hashes[filename] = _sha256_bytes(content)

    combined = "\n".join(f"{name}:{hashes[name]}" for name in sorted(hashes))
    result = ValidatedSources(hashes=hashes, batch_id=_sha256_bytes(combined.encode()))
    for filename, message in read_errors.items():
        result.unusable_files.append(filename)
        result.physical_counts[filename] = 0
        result.rejects.append(
            RejectedRecord(filename, None, "unreadable_file", message, None)
        )
    if "events.jsonl" in contents:
        _validate_jsonl(contents["events.jsonl"], result)
    for filename in ("installs.csv", "funnel_steps.csv"):
        if filename in contents:
            _validate_csv(filename, contents[filename], result)
    return result


DDL = """
CREATE SCHEMA IF NOT EXISTS meta;
CREATE SCHEMA IF NOT EXISTS raw;

CREATE TABLE IF NOT EXISTS meta.source_batches (
    source_batch_id VARCHAR PRIMARY KEY,
    events_sha256 VARCHAR NOT NULL,
    installs_sha256 VARCHAR NOT NULL,
    funnel_steps_sha256 VARCHAR NOT NULL,
    first_seen_at TIMESTAMPTZ NOT NULL,
    promoted_at TIMESTAMPTZ,
    promotion_status VARCHAR NOT NULL,
    events_physical_rows BIGINT NOT NULL,
    installs_physical_rows BIGINT NOT NULL,
    funnel_steps_physical_rows BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS meta.ingestion_runs (
    execution_id VARCHAR PRIMARY KEY,
    source_batch_id VARCHAR NOT NULL,
    mode VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ NOT NULL,
    events_sha256 VARCHAR NOT NULL,
    installs_sha256 VARCHAR NOT NULL,
    funnel_steps_sha256 VARCHAR NOT NULL,
    events_physical_rows BIGINT NOT NULL,
    events_accepted_rows BIGINT NOT NULL,
    events_rejected_rows BIGINT NOT NULL,
    installs_physical_rows BIGINT NOT NULL,
    installs_accepted_rows BIGINT NOT NULL,
    installs_rejected_rows BIGINT NOT NULL,
    funnel_steps_physical_rows BIGINT NOT NULL,
    funnel_steps_accepted_rows BIGINT NOT NULL,
    funnel_steps_rejected_rows BIGINT NOT NULL,
    total_accepted_rows BIGINT NOT NULL,
    total_rejected_rows BIGINT NOT NULL,
    failure_summary VARCHAR
);

CREATE TABLE IF NOT EXISTS raw.events (
    source_batch_id VARCHAR NOT NULL,
    source_line BIGINT NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL,
    raw_line_hash VARCHAR NOT NULL,
    payload JSON NOT NULL,
    PRIMARY KEY (source_batch_id, source_line)
);

CREATE TABLE IF NOT EXISTS raw.rejected_records (
    source_batch_id VARCHAR NOT NULL,
    source_file VARCHAR NOT NULL,
    source_line BIGINT,
    rejection_code VARCHAR NOT NULL,
    rejection_message VARCHAR NOT NULL,
    raw_text VARCHAR,
    raw_text_hash VARCHAR,
    rejected_at TIMESTAMPTZ NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS rejected_record_identity
ON raw.rejected_records (
    source_batch_id, source_file, coalesce(source_line, -1), rejection_code
);

CREATE TABLE IF NOT EXISTS raw.installs (
    source_batch_id VARCHAR NOT NULL,
    source_line BIGINT NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL,
    raw_line_hash VARCHAR NOT NULL,
    user_id VARCHAR,
    install_date VARCHAR,
    platform VARCHAR,
    install_source VARCHAR,
    country VARCHAR,
    PRIMARY KEY (source_batch_id, source_line)
);

CREATE TABLE IF NOT EXISTS raw.funnel_steps (
    source_batch_id VARCHAR NOT NULL,
    source_line BIGINT NOT NULL,
    source_sequence BIGINT NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL,
    raw_line_hash VARCHAR NOT NULL,
    source_step_code VARCHAR,
    event_name VARCHAR,
    PRIMARY KEY (source_batch_id, source_line)
);
"""


def _reject_count(validated: ValidatedSources, filename: str) -> int:
    return sum(1 for reject in validated.rejects if reject.source_file == filename)


def _insert_rejects(
    connection: duckdb.DuckDBPyConnection,
    validated: ValidatedSources,
    now: datetime,
) -> None:
    for reject in validated.rejects:
        connection.execute(
            """
            INSERT OR IGNORE INTO raw.rejected_records VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                validated.batch_id,
                reject.source_file,
                reject.source_line,
                reject.rejection_code,
                reject.rejection_message,
                reject.raw_text,
                _raw_hash(reject.raw_text) if reject.raw_text is not None else None,
                now,
            ],
        )


def _promote_batch(
    connection: duckdb.DuckDBPyConnection,
    validated: ValidatedSources,
    now: datetime,
) -> None:
    connection.executemany(
        "INSERT INTO raw.events VALUES (?, ?, ?, ?, ?::JSON)",
        [
            (validated.batch_id, line, now, raw_hash, payload)
            for line, payload, raw_hash in validated.events
        ],
    )
    connection.executemany(
        "INSERT INTO raw.installs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (validated.batch_id, line, now, raw_hash, *row)
            for line, row, raw_hash in validated.installs
        ],
    )
    connection.executemany(
        "INSERT INTO raw.funnel_steps VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (validated.batch_id, line, sequence, now, raw_hash, *row)
            for sequence, (line, row, raw_hash) in enumerate(validated.funnel_steps, start=1)
        ],
    )


def ingest(
    source_dir: Path,
    database_path: Path,
    mode: Mode = "quarantine",
) -> IngestionResult:
    """Validate and persist one immutable source batch plus an execution audit row."""
    if mode not in {"strict", "quarantine"}:
        raise ValueError(f"unsupported ingestion mode: {mode}")
    started_at = datetime.now(timezone.utc)
    execution_id = str(uuid.uuid4())
    validated = validate_sources(source_dir)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(str(database_path))
    try:
        connection.execute("SET TimeZone='UTC'")
        connection.execute(DDL)
        connection.execute("BEGIN TRANSACTION")
        connection.execute(
            """
            INSERT OR IGNORE INTO meta.source_batches VALUES (
                ?, ?, ?, ?, ?, NULL, 'not_promoted', ?, ?, ?
            )
            """,
            [
                validated.batch_id,
                validated.hashes["events.jsonl"],
                validated.hashes["installs.csv"],
                validated.hashes["funnel_steps.csv"],
                started_at,
                validated.physical_counts.get("events.jsonl", 0),
                validated.physical_counts.get("installs.csv", 0),
                validated.physical_counts.get("funnel_steps.csv", 0),
            ],
        )
        _insert_rejects(connection, validated, started_at)

        already_promoted = connection.execute(
            "SELECT promotion_status = 'promoted' FROM meta.source_batches WHERE source_batch_id = ?",
            [validated.batch_id],
        ).fetchone()[0]
        should_promote = not validated.unusable_files and (
            mode == "quarantine" or not validated.rejects
        )
        # Strict validation remains an execution-level gate even if quarantine
        # previously made this immutable batch queryable.
        if mode == "strict" and validated.rejects:
            status = "rejected"
            promoted = False
            failure_summary = f"strict mode found {len(validated.rejects)} structural reject(s)"
        elif already_promoted:
            status = "already_promoted"
            promoted = True
            failure_summary = None
        elif should_promote:
            _promote_batch(connection, validated, started_at)
            connection.execute(
                """
                UPDATE meta.source_batches
                SET promotion_status = 'promoted', promoted_at = ?
                WHERE source_batch_id = ?
                """,
                [started_at, validated.batch_id],
            )
            status = "promoted"
            promoted = True
            failure_summary = None
        else:
            promoted = False
            if validated.unusable_files:
                status = "unusable"
                failure_summary = "unusable source file(s): " + ", ".join(validated.unusable_files)
            else:
                status = "rejected"
                failure_summary = f"strict mode found {len(validated.rejects)} structural reject(s)"

        completed_at = datetime.now(timezone.utc)
        accepted = {
            "events.jsonl": len(validated.events),
            "installs.csv": len(validated.installs),
            "funnel_steps.csv": len(validated.funnel_steps),
        }
        rejected = {
            name: _reject_count(validated, name)
            for name in ("events.jsonl", "installs.csv", "funnel_steps.csv")
        }
        connection.execute(
            """
            INSERT INTO meta.ingestion_runs VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            [
                execution_id,
                validated.batch_id,
                mode,
                status,
                started_at,
                completed_at,
                validated.hashes["events.jsonl"],
                validated.hashes["installs.csv"],
                validated.hashes["funnel_steps.csv"],
                validated.physical_counts.get("events.jsonl", 0),
                accepted["events.jsonl"],
                rejected["events.jsonl"],
                validated.physical_counts.get("installs.csv", 0),
                accepted["installs.csv"],
                rejected["installs.csv"],
                validated.physical_counts.get("funnel_steps.csv", 0),
                accepted["funnel_steps.csv"],
                rejected["funnel_steps.csv"],
                sum(accepted.values()),
                sum(rejected.values()),
                failure_summary,
            ],
        )
        connection.execute("COMMIT")
    except Exception:
        try:
            connection.execute("ROLLBACK")
        except duckdb.Error:
            pass
        raise
    finally:
        connection.close()

    reject_lines: dict[str, list[int]] = {}
    for reject in validated.rejects:
        if reject.source_line is not None:
            reject_lines.setdefault(reject.source_file, []).append(reject.source_line)
    counts = {
        "events_accepted": len(validated.events),
        "events_rejected": rejected["events.jsonl"],
        "installs_accepted": len(validated.installs),
        "installs_rejected": rejected["installs.csv"],
        "funnel_steps_accepted": len(validated.funnel_steps),
        "funnel_steps_rejected": rejected["funnel_steps.csv"],
    }
    return IngestionResult(
        execution_id=execution_id,
        batch_id=validated.batch_id,
        status=status,
        promoted=promoted,
        counts=counts,
        reject_lines=reject_lines,
        failure_summary=failure_summary,
    )
