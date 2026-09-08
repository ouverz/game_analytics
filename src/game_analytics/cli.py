"""Command-line entry points for ingestion and dbt builds."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from .ingestion import ingest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE = PROJECT_ROOT / "data" / "analytics.duckdb"


def _print_result(result: object) -> None:
    print(f"execution_id={result.execution_id}")
    print(f"source_batch_id={result.batch_id}")
    print(f"status={result.status}")
    for name, count in result.counts.items():
        print(f"{name}={count}")
    for source_file, lines in sorted(result.reject_lines.items()):
        print(f"{source_file} rejected source lines: {', '.join(map(str, lines))}")
    if result.failure_summary:
        print(f"failure={result.failure_summary}")


def _run_ingestion(args: argparse.Namespace) -> int:
    result = ingest(args.source_dir, args.database, args.mode)
    _print_result(result)
    return result.exit_code


def _run_build(args: argparse.Namespace) -> int:
    result = ingest(args.source_dir, args.database, "quarantine")
    _print_result(result)
    if result.exit_code:
        return result.exit_code
    command = [
        "dbt",
        "build",
        "--project-dir",
        str(PROJECT_ROOT / "dbt"),
        "--profiles-dir",
        str(PROJECT_ROOT / "dbt"),
        "--vars",
        f"{{analytics_database: '{args.database.resolve()}'}}",
    ]
    return subprocess.run(command, cwd=PROJECT_ROOT, check=False).returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="game-analytics")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser("ingest", help="validate and ingest source data")
    ingest_parser.add_argument("--mode", choices=("strict", "quarantine"), required=True)
    ingest_parser.add_argument("--source-dir", type=Path, default=PROJECT_ROOT)
    ingest_parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    ingest_parser.set_defaults(handler=_run_ingestion)

    build_parser = subparsers.add_parser("build", help="quarantine ingest followed by dbt build")
    build_parser.add_argument("--source-dir", type=Path, default=PROJECT_ROOT)
    build_parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    build_parser.set_defaults(handler=_run_build)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    raise SystemExit(args.handler(args))
