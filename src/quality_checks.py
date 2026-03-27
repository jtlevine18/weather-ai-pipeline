"""
Post-pipeline data quality checks.

Run after each pipeline execution to verify data integrity.
Each check returns (passed: bool, message: str).
"""

from __future__ import annotations
import logging
from typing import Any, List, Tuple

from src.database.safe_sql import safe_column, safe_table

log = logging.getLogger(__name__)


def check_row_count(conn: Any, table: str,
                    min_expected: int) -> Tuple[bool, str]:
    """Verify table has at least min_expected rows."""
    table = safe_table(table)
    count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    passed = count >= min_expected
    msg = f"{table}: {count} rows (min {min_expected})"
    return passed, msg


def check_null_rate(conn: Any, table: str,
                    column: str, max_null_pct: float) -> Tuple[bool, str]:
    """Verify null rate for a column is below threshold."""
    table, column = safe_table(table), safe_column(column)
    row = conn.execute(f"""
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN {column} IS NULL THEN 1 ELSE 0 END) AS nulls
        FROM {table}
    """).fetchone()
    total, nulls = row[0], row[1]
    if total == 0:
        return True, f"{table}.{column}: no rows to check"
    null_pct = nulls / total * 100
    passed = null_pct <= max_null_pct
    msg = f"{table}.{column}: {null_pct:.1f}% null (max {max_null_pct}%)"
    return passed, msg


def check_value_range(conn: Any, table: str,
                      column: str, min_val: float, max_val: float) -> Tuple[bool, str]:
    """Verify all non-null values in column are within [min_val, max_val]."""
    table, column = safe_table(table), safe_column(column)
    row = conn.execute(f"""
        SELECT MIN({column}), MAX({column})
        FROM {table}
        WHERE {column} IS NOT NULL
    """).fetchone()
    if row[0] is None:
        return True, f"{table}.{column}: no non-null values"
    actual_min, actual_max = row[0], row[1]
    passed = actual_min >= min_val and actual_max <= max_val
    msg = f"{table}.{column}: range [{actual_min:.1f}, {actual_max:.1f}] (expected [{min_val}, {max_val}])"
    return passed, msg


def check_freshness(conn: Any, table: str,
                    ts_column: str, max_age_hours: float) -> Tuple[bool, str]:
    """Verify most recent row is not older than max_age_hours."""
    table, ts_column = safe_table(table), safe_column(ts_column)
    row = conn.execute(f"""
        SELECT MAX({ts_column}) FROM {table}
    """).fetchone()
    if row[0] is None:
        return False, f"{table}: no data"
    from datetime import datetime, timedelta, timezone
    latest = row[0]
    if isinstance(latest, str):
        latest = datetime.fromisoformat(latest)
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    age_hours = (now - latest).total_seconds() / 3600
    passed = age_hours <= max_age_hours
    msg = f"{table}: latest {ts_column} is {age_hours:.1f}h old (max {max_age_hours}h)"
    return passed, msg


def run_all_checks(conn: Any) -> List[Tuple[bool, str]]:
    """Run all quality checks and return results."""
    results = []

    # Row counts — pipeline should produce data for 20 stations
    results.append(check_row_count(conn, "raw_telemetry", 15))
    results.append(check_row_count(conn, "clean_telemetry", 10))
    results.append(check_row_count(conn, "forecasts", 10))

    # Null rates — healed data should have low null rates
    results.append(check_null_rate(conn, "clean_telemetry", "temperature", 10.0))
    results.append(check_null_rate(conn, "clean_telemetry", "humidity", 15.0))

    # Value ranges — physical bounds
    results.append(check_value_range(conn, "clean_telemetry", "temperature", -10.0, 55.0))
    results.append(check_value_range(conn, "clean_telemetry", "humidity", 0.0, 100.0))
    results.append(check_value_range(conn, "clean_telemetry", "quality_score", 0.0, 1.0))
    results.append(check_value_range(conn, "forecasts", "confidence", 0.0, 1.0))

    # Log results
    passed_count = sum(1 for p, _ in results if p)
    total = len(results)
    for passed, msg in results:
        level = logging.INFO if passed else logging.WARNING
        status = "PASS" if passed else "FAIL"
        log.log(level, "[%s] %s", status, msg)

    log.info("Quality checks: %d/%d passed", passed_count, total)
    return results
