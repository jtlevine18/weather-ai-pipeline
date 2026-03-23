#!/usr/bin/env python3
"""DVC stage: export joined clean_telemetry + forecasts to Parquet for MOS training."""

from __future__ import annotations

import os
import sys

# Allow imports from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import duckdb

DB_PATH = "weather.duckdb"
OUT_PATH = "data/training_export.parquet"

JOIN_QUERY = """
SELECT
    c.station_id,
    c.ts                                        AS obs_ts,
    c.temperature                               AS actual_temp,
    c.humidity,
    c.wind_speed,
    c.wind_dir,
    c.pressure,
    c.rainfall                                  AS actual_rainfall,
    c.quality_score,
    f.temperature                               AS nwp_temp,
    f.rainfall                                  AS nwp_rainfall,
    f.model_used,
    f.correction                                AS prior_correction,
    f.confidence,
    f.issued_at                                 AS forecast_issued_at
FROM clean_telemetry c
INNER JOIN forecasts f
    ON  c.station_id = f.station_id
    AND date_trunc('hour', c.ts) = date_trunc('hour', f.issued_at)
WHERE c.temperature IS NOT NULL
  AND f.temperature IS NOT NULL
ORDER BY c.station_id, c.ts
"""


def main() -> None:
    if not os.path.exists(DB_PATH):
        print(f"ERROR: Database not found at {DB_PATH}")
        sys.exit(1)

    # Ensure output directory exists
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)

    conn = duckdb.connect(DB_PATH, read_only=True)

    # Quick sanity check: are there rows in both source tables?
    clean_count = conn.execute("SELECT COUNT(*) FROM clean_telemetry").fetchone()[0]
    forecast_count = conn.execute("SELECT COUNT(*) FROM forecasts").fetchone()[0]
    print(f"Source rows — clean_telemetry: {clean_count}, forecasts: {forecast_count}")

    if clean_count == 0 or forecast_count == 0:
        print("ERROR: One or both source tables are empty. Run the pipeline first.")
        conn.close()
        sys.exit(1)

    # Export joined result to Parquet
    conn.execute(f"COPY ({JOIN_QUERY}) TO '{OUT_PATH}' (FORMAT PARQUET)")

    # Print summary
    result = conn.execute(
        f"SELECT COUNT(*) AS rows FROM read_parquet('{OUT_PATH}')"
    ).fetchone()
    row_count = result[0]

    cols = conn.execute(
        f"SELECT * FROM read_parquet('{OUT_PATH}') LIMIT 0"
    ).description
    col_names = [d[0] for d in cols]

    conn.close()

    file_size_kb = os.path.getsize(OUT_PATH) / 1024
    print(f"Exported {row_count} rows, {len(col_names)} columns to {OUT_PATH}")
    print(f"Columns: {', '.join(col_names)}")
    print(f"File size: {file_size_kb:.1f} KB")


if __name__ == "__main__":
    main()
