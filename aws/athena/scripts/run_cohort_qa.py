#!/usr/bin/env python3
"""Run Athena QA queries for CPIC time-to-event cohort and model-event parquet outputs."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import boto3


DEFAULT_DATABASE = "cohorts"
DEFAULT_WORKGROUP = "APCD"
DEFAULT_REGION = "us-east-1"
DEFAULT_OUTPUT_LOCATION = (
    "s3://aws-athena-query-results-us-east-1-535362115856/cpic_time_to_event_qa/"
)

SQL_DIR = Path(__file__).resolve().parents[1] / "sql"
SETUP_SQL_FILES = [
    SQL_DIR / "create_cohort_qa_tables.sql",
    SQL_DIR / "create_model_events_qa_tables.sql",
]
QA_SQL_FILES = [
    SQL_DIR / "qa_combined_cohort_coverage.sql",
    SQL_DIR / "qa_falls_cohort.sql",
    SQL_DIR / "qa_ed_cohort.sql",
    SQL_DIR / "qa_model_events_coverage.sql",
]


def split_sql_statements(sql_text: str) -> list[str]:
    """Split simple Athena SQL files into individual statements."""
    statements: list[str] = []
    current: list[str] = []

    for line in sql_text.splitlines():
        current.append(line)
        if line.rstrip().endswith(";"):
            statement = "\n".join(current).strip().rstrip(";").strip()
            if statement:
                statements.append(statement)
            current = []

    tail = "\n".join(current).strip()
    if tail:
        statements.append(tail)

    return statements


def run_athena_query(
    athena,
    sql: str,
    *,
    database: str,
    workgroup: str,
    output_location: str,
    label: str,
    max_wait_seconds: int,
) -> str:
    print(f"\n--- {label} ---", flush=True)
    response = athena.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={"Database": database},
        ResultConfiguration={"OutputLocation": output_location},
        WorkGroup=workgroup,
    )
    query_execution_id = response["QueryExecutionId"]
    start = time.time()

    while True:
        query = athena.get_query_execution(QueryExecutionId=query_execution_id)["QueryExecution"]
        state = query["Status"]["State"]
        if state in {"SUCCEEDED", "FAILED", "CANCELLED"}:
            break
        if time.time() - start > max_wait_seconds:
            raise TimeoutError(f"Timed out waiting for {query_execution_id}: {label}")
        time.sleep(2)

    print(f"state={state} query_execution_id={query_execution_id}", flush=True)
    if state != "SUCCEEDED":
        reason = query["Status"].get("StateChangeReason", "")
        raise RuntimeError(f"Athena query failed for {label}: {reason}")

    return query_execution_id


def is_result_query(sql: str) -> bool:
    """Return True when a statement should emit rows."""
    for line in sql.splitlines():
        stripped = line.strip().lower()
        if not stripped or stripped.startswith("--"):
            continue
        return stripped.startswith(("select", "with"))
    return False


def print_query_results(athena, query_execution_id: str, max_rows: int) -> None:
    rows_printed = 0
    paginator = athena.get_paginator("get_query_results")
    for page in paginator.paginate(QueryExecutionId=query_execution_id):
        for row in page["ResultSet"]["Rows"]:
            if rows_printed >= max_rows:
                print(f"... truncated after {max_rows} rows", flush=True)
                return
            print("\t".join(cell.get("VarCharValue", "") for cell in row.get("Data", [])), flush=True)
            rows_printed += 1


def run_sql_file(athena, sql_file: Path, args: argparse.Namespace, *, print_results: bool) -> None:
    statements = split_sql_statements(sql_file.read_text(encoding="utf-8"))
    for idx, statement in enumerate(statements, start=1):
        label = f"{sql_file.name} statement {idx}/{len(statements)}"
        query_id = run_athena_query(
            athena,
            statement,
            database=args.database,
            workgroup=args.workgroup,
            output_location=args.output_location,
            label=label,
            max_wait_seconds=args.max_wait_seconds,
        )
        if print_results and is_result_query(statement):
            print_query_results(athena, query_id, args.max_rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default=DEFAULT_DATABASE)
    parser.add_argument("--workgroup", default=DEFAULT_WORKGROUP)
    parser.add_argument("--region", default=DEFAULT_REGION)
    parser.add_argument("--output-location", default=DEFAULT_OUTPUT_LOCATION)
    parser.add_argument("--skip-ddl", action="store_true", help="Skip CREATE TABLE/MSCK setup SQL.")
    parser.add_argument(
        "--qa-file",
        action="append",
        default=None,
        help="Run a specific SQL file from aws/athena/sql. Can be passed multiple times.",
    )
    parser.add_argument("--max-wait-seconds", type=int, default=180)
    parser.add_argument("--max-rows", type=int, default=120)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    athena = boto3.client("athena", region_name=args.region)

    if not args.skip_ddl:
        for setup_sql in SETUP_SQL_FILES:
            run_sql_file(athena, setup_sql, args, print_results=False)

    qa_files = [SQL_DIR / name for name in args.qa_file] if args.qa_file else QA_SQL_FILES
    for sql_file in qa_files:
        if not sql_file.exists():
            raise FileNotFoundError(sql_file)
        run_sql_file(athena, sql_file, args, print_results=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
