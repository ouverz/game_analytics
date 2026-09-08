from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from game_analytics.ingestion import ingest, validate_sources


VALID_EVENT = {
    "event_name": "INIT_CLIENT_START",
    "user_id": 1,
    "session_id": "s_1_001",
    "timestamp": "2026-06-09T00:00:00Z",
}


def write_sources(
    directory: Path,
    event_lines: list[str] | None = None,
    installs: str | None = None,
    funnel_steps: str | None = None,
) -> None:
    lines = event_lines if event_lines is not None else [json.dumps(VALID_EVENT)]
    (directory / "events.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (directory / "installs.csv").write_text(
        installs
        or "user_id,install_date,platform,install_source,country\n"
        "1,2026-06-09,iOS,organic,DE\n",
        encoding="utf-8",
    )
    (directory / "funnel_steps.csv").write_text(
        funnel_steps or "step_order,event_name\n1,INIT_CLIENT_START\n",
        encoding="utf-8",
    )


def test_valid_input_is_promoted_in_strict_mode(tmp_path: Path) -> None:
    write_sources(tmp_path)
    result = ingest(tmp_path, tmp_path / "analytics.duckdb", "strict")

    assert result.exit_code == 0
    assert result.status == "promoted"
    assert result.counts["events_accepted"] == 1
    assert result.counts["events_rejected"] == 0


@pytest.mark.parametrize(
    ("bad_line", "expected_code"),
    [
        ('{"event_name": "INIT_CLIENT_START"', "invalid_json"),
        ('{"event_name": "INIT_CLIENT_START",}', "invalid_json"),
        ("", "blank_line"),
        ('["not", "an", "object"]', "non_object_json"),
        ('"scalar"', "non_object_json"),
    ],
)
def test_jsonl_structural_rejections(
    tmp_path: Path, bad_line: str, expected_code: str
) -> None:
    write_sources(tmp_path, [json.dumps(VALID_EVENT), bad_line])

    validated = validate_sources(tmp_path)

    assert len(validated.events) == 1
    assert [reject.rejection_code for reject in validated.rejects] == [expected_code]


def test_csv_header_error_makes_file_unusable(tmp_path: Path) -> None:
    write_sources(tmp_path, installs="wrong,headers\n1,value\n")

    result = ingest(tmp_path, tmp_path / "analytics.duckdb", "quarantine")

    assert result.exit_code == 1
    assert result.status == "unusable"
    assert result.promoted is False


def test_csv_width_error_is_quarantined(tmp_path: Path) -> None:
    write_sources(
        tmp_path,
        installs=(
            "user_id,install_date,platform,install_source,country\n"
            "1,2026-06-09,iOS,organic,DE\n"
            "2,2026-06-09,Android,organic\n"
        ),
    )

    result = ingest(tmp_path, tmp_path / "analytics.duckdb", "quarantine")

    assert result.exit_code == 0
    assert result.counts["installs_accepted"] == 1
    assert result.counts["installs_rejected"] == 1


def test_strict_records_rejects_but_does_not_promote(tmp_path: Path) -> None:
    write_sources(tmp_path, [json.dumps(VALID_EVENT), "{truncated"])
    database = tmp_path / "analytics.duckdb"

    result = ingest(tmp_path, database, "strict")

    assert result.exit_code == 1
    assert result.status == "rejected"
    with duckdb.connect(str(database), read_only=True) as connection:
        assert connection.execute("select count(*) from raw.events").fetchone()[0] == 0
        assert connection.execute("select count(*) from raw.rejected_records").fetchone()[0] == 1
        assert connection.execute(
            "select promotion_status from meta.source_batches"
        ).fetchone()[0] == "not_promoted"


def test_quarantine_promotes_only_structurally_valid_rows(tmp_path: Path) -> None:
    write_sources(tmp_path, [json.dumps(VALID_EVENT), "{truncated"])
    database = tmp_path / "analytics.duckdb"

    result = ingest(tmp_path, database, "quarantine")

    assert result.exit_code == 0
    assert result.status == "promoted"
    with duckdb.connect(str(database), read_only=True) as connection:
        assert connection.execute("select count(*) from raw.events").fetchone()[0] == 1
        assert connection.execute("select count(*) from raw.installs").fetchone()[0] == 1
        assert connection.execute("select count(*) from raw.funnel_steps").fetchone()[0] == 1


def test_rerun_records_execution_without_duplicating_batch_rows(tmp_path: Path) -> None:
    write_sources(tmp_path)
    database = tmp_path / "analytics.duckdb"

    first = ingest(tmp_path, database, "quarantine")
    second = ingest(tmp_path, database, "quarantine")

    assert first.batch_id == second.batch_id
    assert first.execution_id != second.execution_id
    assert second.status == "already_promoted"
    with duckdb.connect(str(database), read_only=True) as connection:
        assert connection.execute("select count(*) from meta.source_batches").fetchone()[0] == 1
        assert connection.execute("select count(*) from meta.ingestion_runs").fetchone()[0] == 2
        assert connection.execute("select count(*) from raw.events").fetchone()[0] == 1


def test_strict_rerun_still_fails_after_quarantine_promotion(tmp_path: Path) -> None:
    write_sources(tmp_path, [json.dumps(VALID_EVENT), "{truncated"])
    database = tmp_path / "analytics.duckdb"
    assert ingest(tmp_path, database, "quarantine").exit_code == 0

    strict_result = ingest(tmp_path, database, "strict")

    assert strict_result.exit_code == 1
    assert strict_result.status == "rejected"
    with duckdb.connect(str(database), read_only=True) as connection:
        assert connection.execute("select count(*) from raw.events").fetchone()[0] == 1
        assert connection.execute("select count(*) from meta.ingestion_runs").fetchone()[0] == 2
