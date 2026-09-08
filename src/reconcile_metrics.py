"""Independently reconcile the launch metrics directly from the raw files.

This intentionally does not query the DuckDB/dbt models. It provides a small,
human-readable second implementation of the eligibility and sequential-funnel
rules used for the stakeholder-facing results.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd


WINDOW_START = pd.Timestamp("2026-06-09T00:00:00Z")
WINDOW_END = pd.Timestamp("2026-06-23T00:00:00Z")

PRIMARY_STEPS = [
    ("client_start", "INIT_CLIENT_START"),
    ("config_loaded", "INIT_CONFIG_LOADED"),
    ("localization_complete", "INIT_LOCALIZATION_END"),
    ("maintenance_check", "INIT_UPDATE_MAINTENANCE_CHECK"),
    ("data_load_started", "INIT_DATA_MODEL_LOAD_START"),
    ("data_load_complete", "INIT_DATA_MODEL_LOAD_END"),
    ("ready_to_start", "INIT_READY_TO_START"),
    ("login_started", "INIT_PLAYER_LOGIN_START"),
    ("login_complete", "INIT_PLAYER_LOGIN_END"),
    ("game_joined", "INIT_GAME_JOINED"),
]

BRANCH_OUTCOMES = {
    "maintenance_blocked": "INIT_UPDATE_MAINTENANCE_BLOCKED",
    "patch_declined": "INIT_ASSET_PATCH_SIZE_DECLINED",
    "patch_failed": "INIT_ASSET_PATCH_FAILED",
    "data_load_failed": "INIT_DATA_MODEL_LOAD_FAILED",
    "privacy_declined": "INIT_PRIVACY_POLICY_DIALOGUE_DECLINED",
    "tracking_denied_ios": "APPLE_TRACKING_STATUS_DENIED",
}

CORE_ACTION_EVENT = "BATTLE_STARTED"


def safe_rate(numerator: int, denominator: int) -> float | None:
    """Return a consistently rounded rate or null for an empty denominator."""
    return round(numerator / denominator, 6) if denominator else None


def rounded_stat(value: float) -> float | None:
    """Return a presentation-ready statistic while preserving empty samples."""
    return None if pd.isna(value) else round(float(value), 2)


def read_events(path: Path) -> tuple[pd.DataFrame, dict[str, int]]:
    """Read valid JSON objects and retain only non-sensitive working fields."""
    records: list[dict[str, Any]] = []
    physical_rows = 0
    malformed_rows = 0

    with path.open(encoding="utf-8") as source:
        for source_line, raw_line in enumerate(source, start=1):
            physical_rows += 1
            raw_text = raw_line.rstrip("\r\n")
            try:
                payload = json.loads(raw_text)
            except json.JSONDecodeError:
                malformed_rows += 1
                continue
            if not isinstance(payload, dict):
                malformed_rows += 1
                continue
            records.append(
                {
                    "source_line": source_line,
                    "raw_hash": hashlib.sha256(raw_text.encode()).hexdigest(),
                    "event_name": payload.get("event_name"),
                    "user_id": pd.to_numeric(payload.get("user_id"), errors="coerce"),
                    "session_id": payload.get("session_id"),
                    "raw_timestamp": payload.get("timestamp"),
                    "platform": payload.get("platform"),
                    "client_version": payload.get("client_version"),
                }
            )

    events = pd.DataFrame(records)
    timestamp_text = events["raw_timestamp"].astype("string").str.strip()
    is_epoch_ms = timestamp_text.str.fullmatch(r"\d{13}", na=False)
    events["event_ts"] = pd.to_datetime(
        timestamp_text.where(~is_epoch_ms),
        format="mixed",
        utc=True,
        errors="coerce",
    )
    events.loc[is_epoch_ms, "event_ts"] = pd.to_datetime(
        timestamp_text[is_epoch_ms].astype("int64"),
        unit="ms",
        utc=True,
        errors="coerce",
    )

    # Timing is excluded if any structurally usable row makes the session's
    # source-order clock move backwards. This deliberately conservative flag is
    # calculated before metric exclusions, matching the dbt timing contract.
    reversal_input = events[
        ["source_line", "user_id", "session_id", "event_ts"]
    ].sort_values("source_line")
    reversal_input["previous_ts"] = reversal_input.groupby(
        ["user_id", "session_id"], dropna=False
    )["event_ts"].shift()
    reversal_input["row_has_time_reversal"] = (
        reversal_input["event_ts"] < reversal_input["previous_ts"]
    )
    events["raw_session_has_time_reversal"] = reversal_input.groupby(
        ["user_id", "session_id"], dropna=False
    )["row_has_time_reversal"].transform("any")

    later_duplicate = events.duplicated("raw_hash", keep="first")
    out_of_window = events["event_ts"].notna() & ~events["event_ts"].between(
        WINDOW_START, WINDOW_END, inclusive="left"
    )
    required_fields = events[
        ["event_name", "user_id", "session_id", "event_ts"]
    ].notna().all(axis=1)
    eligible = required_fields & ~later_duplicate & ~out_of_window

    quality = {
        "physical_event_rows": physical_rows,
        "valid_json_objects": len(events),
        "malformed_rows": malformed_rows,
        "later_exact_duplicate_rows": int(later_duplicate.sum()),
        "out_of_window_rows": int(out_of_window.sum()),
        "metric_eligible_rows": int(eligible.sum()),
    }
    return events.loc[eligible].copy(), quality


def read_installs(path: Path) -> pd.DataFrame:
    """Read one normalized install row per usable user identifier."""
    installs = pd.read_csv(path)
    installs["user_id"] = pd.to_numeric(installs["user_id"], errors="coerce")
    installs["install_date"] = pd.to_datetime(
        installs["install_date"], utc=True, errors="coerce"
    ).dt.normalize()
    installs["install_platform"] = installs["platform"].replace(
        {"ios": "iOS", "IOS": "iOS", "android": "Android"}
    )
    return installs.dropna(subset=["user_id"]).drop_duplicates(
        "user_id", keep="first"
    )


def session_table(events: pd.DataFrame) -> pd.DataFrame:
    """Create one row per logical user/session with sequential funnel flags."""
    keys = ["user_id", "session_id"]
    events = events.sort_values("source_line")
    sessions = events.groupby(keys, dropna=False).agg(
        session_has_time_reversal=("raw_session_has_time_reversal", "any"),
    )
    earliest_metadata = (
        events.sort_values(["event_ts", "source_line"])
        .groupby(keys, dropna=False)[["platform", "client_version"]]
        .first()
    )
    sessions = sessions.join(earliest_metadata)

    first_event_times = (
        events[events["event_name"].isin(
            [event for _, event in PRIMARY_STEPS]
            + list(BRANCH_OUTCOMES.values())
            + [CORE_ACTION_EVENT]
        )]
        .pivot_table(
            index=keys,
            columns="event_name",
            values="event_ts",
            aggfunc="min",
        )
    )
    sessions = sessions.join(first_event_times)

    previous_time: pd.Series | None = None
    previous_reached: pd.Series | None = None
    for step_key, event_name in PRIMARY_STEPS:
        event_time = sessions.get(event_name)
        if event_time is None:
            event_time = pd.Series(
                pd.NaT,
                index=sessions.index,
                dtype="datetime64[ns, UTC]",
            )
        if previous_time is None:
            reached = event_time.notna()
        else:
            assert previous_reached is not None
            reached = (
                previous_reached
                & event_time.notna()
                & (event_time >= previous_time)
            )
        sessions[f"reached_{step_key}"] = reached
        previous_time = event_time
        previous_reached = reached

    sessions["loading_seconds"] = (
        sessions["INIT_GAME_JOINED"] - sessions["INIT_CLIENT_START"]
    ).dt.total_seconds()
    sessions["timing_eligible"] = (
        sessions["reached_game_joined"]
        & ~sessions["session_has_time_reversal"]
        & sessions["loading_seconds"].ge(0)
    )
    return sessions


def calculate_ftue_metrics(
    events: pd.DataFrame,
    sessions: pd.DataFrame,
    installs: pd.DataFrame,
    observation_end: pd.Timestamp = WINDOW_END,
) -> dict[str, int | float | None]:
    """Calculate the minimum defensible first-time-user-experience KPIs."""
    install_users = installs[["user_id", "install_date"]].copy()
    install_users = install_users.dropna(subset=["user_id", "install_date"])

    first_sessions = sessions.reset_index()
    first_sessions = first_sessions[
        first_sessions["INIT_CLIENT_START"].notna()
    ].merge(install_users[["user_id"]], on="user_id", how="inner")
    first_sessions = (
        first_sessions.sort_values(
            ["user_id", "INIT_CLIENT_START", "session_id"]
        )
        .drop_duplicates("user_id", keep="first")
        .copy()
    )

    qualifying_battles = events[events["event_name"].eq(CORE_ACTION_EVENT)][
        ["user_id", "session_id", "event_ts"]
    ].merge(
        first_sessions[
            [
                "user_id",
                "session_id",
                "INIT_CLIENT_START",
                "INIT_GAME_JOINED",
                "reached_game_joined",
            ]
        ],
        on=["user_id", "session_id"],
        how="inner",
    )
    qualifying_battles = qualifying_battles[
        qualifying_battles["reached_game_joined"]
        & qualifying_battles["event_ts"].ge(
            qualifying_battles["INIT_GAME_JOINED"]
        )
    ]
    first_battles = (
        qualifying_battles.groupby("user_id", as_index=False)["event_ts"]
        .min()
        .rename(columns={"event_ts": "first_battle_at"})
    )
    activated = first_sessions.merge(first_battles, on="user_id", how="inner")
    time_to_battle = (
        activated["first_battle_at"] - activated["INIT_CLIENT_START"]
    ).dt.total_seconds()

    eligible_new_players = len(first_sessions)
    first_session_game_entries = int(
        first_sessions["reached_game_joined"].sum()
    )
    first_session_activations = len(activated)

    mature_installs = install_users[
        install_users["install_date"] + pd.Timedelta(days=1) < observation_end
    ].copy()
    return_starts = events[events["event_name"].eq("INIT_CLIENT_START")][
        ["user_id", "event_ts"]
    ].copy()
    return_starts["event_date"] = return_starts["event_ts"].dt.normalize()
    d1_candidates = mature_installs.merge(
        return_starts[["user_id", "event_date"]], on="user_id", how="left"
    )
    d1_candidates["returned_on_d1"] = d1_candidates["event_date"].eq(
        d1_candidates["install_date"] + pd.Timedelta(days=1)
    )
    returned_by_user = d1_candidates.groupby("user_id")["returned_on_d1"].any()
    d1_returned_players = int(returned_by_user.sum())

    return {
        "eligible_new_players": eligible_new_players,
        "first_session_game_entries": first_session_game_entries,
        "first_session_game_entry_rate": safe_rate(
            first_session_game_entries, eligible_new_players
        ),
        "first_session_activations": first_session_activations,
        "first_session_activation_rate": safe_rate(
            first_session_activations, eligible_new_players
        ),
        "activation_rate_among_game_entries": safe_rate(
            first_session_activations, first_session_game_entries
        ),
        "median_time_to_first_battle_seconds": rounded_stat(
            time_to_battle.median()
        ),
        "p90_time_to_first_battle_seconds": rounded_stat(
            time_to_battle.quantile(0.90)
        ),
        "activation_timing_sample_size": len(time_to_battle),
        "d1_mature_installs": len(mature_installs),
        "d1_returned_players": d1_returned_players,
        "d1_retention_rate": safe_rate(
            d1_returned_players, len(mature_installs)
        ),
    }


def calculate_metrics(
    events: pd.DataFrame,
    sessions: pd.DataFrame,
    quality: dict[str, int],
    installs_path: Path,
) -> dict[str, Any]:
    """Return aggregate reconciliation metrics without raw identifiers."""
    funnel: list[dict[str, Any]] = []
    starting_sessions = int(sessions["reached_client_start"].sum())
    previous_sessions = starting_sessions
    for step_key, _ in PRIMARY_STEPS:
        count = int(sessions[f"reached_{step_key}"].sum())
        funnel.append(
            {
                "step": step_key,
                "sessions": count,
                "drop_off_sessions": previous_sessions - count,
                "step_conversion_rate": round(count / previous_sessions, 6)
                if previous_sessions
                else None,
                "start_conversion_rate": round(count / starting_sessions, 6)
                if starting_sessions
                else None,
            }
        )
        previous_sessions = count

    joined_sessions = int(sessions["reached_game_joined"].sum())
    durations = sessions.loc[sessions["timing_eligible"], "loading_seconds"]
    branches: list[dict[str, Any]] = []
    for branch_key, event_name in BRANCH_OUTCOMES.items():
        observed = sessions[event_name].notna()
        continued = observed & sessions["INIT_GAME_JOINED"].gt(sessions[event_name])
        branches.append(
            {
                "outcome": branch_key,
                "observed_sessions": int(observed.sum()),
                "continued_sessions": int(continued.sum()),
                "continuation_rate": round(float(continued.sum() / observed.sum()), 6)
                if observed.any()
                else None,
            }
        )

    installs = read_installs(installs_path)
    segmented = sessions.reset_index().merge(
        installs[["user_id", "install_platform"]], on="user_id", how="left"
    )
    segmented = segmented[
        segmented["install_platform"].notna()
        & segmented["platform"].notna()
        & segmented["platform"].eq(segmented["install_platform"])
    ]
    segment_rows: list[dict[str, Any]] = []
    for (platform, client_version), group in segmented.groupby(
        ["platform", "client_version"], dropna=False
    ):
        started = int(group["reached_client_start"].sum())
        joined = int(group["reached_game_joined"].sum())
        timing = group.loc[group["timing_eligible"], "loading_seconds"]
        segment_rows.append(
            {
                "platform": platform,
                "client_version": client_version,
                "started_sessions": started,
                "joined_sessions": joined,
                "conversion_rate": round(joined / started, 6) if started else None,
                "median_loading_seconds": round(float(timing.median()), 2),
                "p90_loading_seconds": round(float(timing.quantile(0.90)), 2),
            }
        )

    return {
        "quality": quality,
        "headline": {
            "started_sessions": starting_sessions,
            "joined_sessions": joined_sessions,
            "conversion_rate": round(joined_sessions / starting_sessions, 6),
            "timed_sessions": int(sessions["timing_eligible"].sum()),
            "median_loading_seconds": round(float(durations.median()), 2),
            "p90_loading_seconds": round(float(durations.quantile(0.90)), 2),
            "p95_loading_seconds": round(float(durations.quantile(0.95)), 2),
        },
        "primary_funnel": funnel,
        "conditional_outcomes": branches,
        "platform_version_segments": segment_rows,
        "ftue_kpis": calculate_ftue_metrics(events, sessions, installs),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, default=Path("events.jsonl"))
    parser.add_argument("--installs", type=Path, default=Path("installs.csv"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/metric_reconciliation.json"),
    )
    args = parser.parse_args()

    events, quality = read_events(args.events)
    sessions = session_table(events)
    metrics = calculate_metrics(
        events, sessions, quality, args.installs
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metrics["headline"], indent=2))
    print(json.dumps(metrics["ftue_kpis"], indent=2))
    print(f"Wrote aggregate reconciliation: {args.output}")


if __name__ == "__main__":
    main()
