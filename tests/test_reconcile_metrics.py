from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from reconcile_metrics import calculate_ftue_metrics, read_events


def timestamp(value: str) -> pd.Timestamp:
    return pd.Timestamp(value)


def make_sessions(rows: list[dict[str, object]]) -> pd.DataFrame:
    sessions = pd.DataFrame(rows).set_index(["user_id", "session_id"])
    sessions["INIT_CLIENT_START"] = pd.to_datetime(
        sessions["INIT_CLIENT_START"], utc=True
    )
    sessions["INIT_GAME_JOINED"] = pd.to_datetime(
        sessions["INIT_GAME_JOINED"], utc=True
    )
    return sessions


def make_installs(rows: list[tuple[int, str]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["user_id", "install_date"]).assign(
        install_date=lambda frame: pd.to_datetime(
            frame["install_date"], utc=True
        )
    )


def test_ftue_uses_first_observed_launch_not_later_success() -> None:
    sessions = make_sessions(
        [
            {
                "user_id": 1,
                "session_id": "first",
                "INIT_CLIENT_START": "2026-06-09T00:00:00Z",
                "INIT_GAME_JOINED": None,
                "reached_game_joined": False,
            },
            {
                "user_id": 1,
                "session_id": "later",
                "INIT_CLIENT_START": "2026-06-10T00:00:00Z",
                "INIT_GAME_JOINED": "2026-06-10T00:01:00Z",
                "reached_game_joined": True,
            },
            {
                "user_id": 2,
                "session_id": "first",
                "INIT_CLIENT_START": "2026-06-09T00:00:00Z",
                "INIT_GAME_JOINED": "2026-06-09T00:01:00Z",
                "reached_game_joined": True,
            },
        ]
    )
    events = pd.DataFrame(
        [
            (1, "later", "BATTLE_STARTED", "2026-06-10T00:02:00Z"),
            (2, "first", "BATTLE_STARTED", "2026-06-09T00:02:00Z"),
        ],
        columns=["user_id", "session_id", "event_name", "event_ts"],
    )
    events["event_ts"] = pd.to_datetime(events["event_ts"], utc=True)

    result = calculate_ftue_metrics(
        events,
        sessions,
        make_installs([(1, "2026-06-09"), (2, "2026-06-09")]),
    )

    assert result["eligible_new_players"] == 2
    assert result["first_session_game_entries"] == 1
    assert result["first_session_activations"] == 1


def test_activation_requires_battle_after_game_entry_in_same_session() -> None:
    sessions = make_sessions(
        [
            {
                "user_id": 1,
                "session_id": "first",
                "INIT_CLIENT_START": "2026-06-09T00:00:00Z",
                "INIT_GAME_JOINED": "2026-06-09T00:01:00Z",
                "reached_game_joined": True,
            }
        ]
    )
    events = pd.DataFrame(
        [
            (1, "first", "BATTLE_STARTED", "2026-06-09T00:00:30Z"),
            (1, "other", "BATTLE_STARTED", "2026-06-09T00:01:30Z"),
            (1, "first", "BATTLE_STARTED", "2026-06-09T00:02:00Z"),
        ],
        columns=["user_id", "session_id", "event_name", "event_ts"],
    )
    events["event_ts"] = pd.to_datetime(events["event_ts"], utc=True)

    result = calculate_ftue_metrics(
        events, sessions, make_installs([(1, "2026-06-09")])
    )

    assert result["first_session_activations"] == 1
    assert result["median_time_to_first_battle_seconds"] == 120.0


def test_event_eligibility_excludes_bad_duplicate_and_out_of_window_rows(
    tmp_path: Path,
) -> None:
    valid = {
        "event_name": "INIT_CLIENT_START",
        "user_id": 1,
        "session_id": "first",
        "timestamp": "2026-06-09T00:00:00Z",
    }
    out_of_window = {**valid, "timestamp": "2026-06-23T00:00:00Z"}
    invalid_timestamp = {**valid, "timestamp": "not-a-time"}
    lines = [
        json.dumps(valid),
        json.dumps(valid),
        json.dumps(out_of_window),
        json.dumps(invalid_timestamp),
        "{malformed",
    ]
    path = tmp_path / "events.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    events, quality = read_events(path)

    assert len(events) == 1
    assert quality["malformed_rows"] == 1
    assert quality["later_exact_duplicate_rows"] == 1
    assert quality["out_of_window_rows"] == 1
    assert quality["metric_eligible_rows"] == 1


def test_d1_retention_uses_only_fully_mature_install_cohorts() -> None:
    sessions = make_sessions(
        [
            {
                "user_id": user_id,
                "session_id": "first",
                "INIT_CLIENT_START": f"2026-01-0{user_id}T00:00:00Z",
                "INIT_GAME_JOINED": None,
                "reached_game_joined": False,
            }
            for user_id in (1, 2, 3)
        ]
    )
    events = pd.DataFrame(
        [
            (1, "return", "INIT_CLIENT_START", "2026-01-02T12:00:00Z"),
            (2, "return", "INIT_CLIENT_START", "2026-01-04T12:00:00Z"),
            (99, "return", "INIT_CLIENT_START", "2026-01-02T12:00:00Z"),
        ],
        columns=["user_id", "session_id", "event_name", "event_ts"],
    )
    events["event_ts"] = pd.to_datetime(events["event_ts"], utc=True)

    result = calculate_ftue_metrics(
        events,
        sessions,
        make_installs(
            [(1, "2026-01-01"), (2, "2026-01-02"), (3, "2026-01-03")]
        ),
        observation_end=timestamp("2026-01-04T00:00:00Z"),
    )

    assert result["d1_mature_installs"] == 2
    assert result["d1_returned_players"] == 1
    assert result["d1_retention_rate"] == 0.5
