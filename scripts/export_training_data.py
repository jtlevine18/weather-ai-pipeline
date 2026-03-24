#!/usr/bin/env python3
"""DVC stage: export joined clean_telemetry + forecasts to Parquet for MOS training.

Queries PostgreSQL (DATABASE_URL), joins day-0 forecasts against observations,
and writes the result to Parquet for train_mos.py to consume.
"""

from __future__ import annotations

import os
import sys

# Allow imports from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
from src.database._util import get_database_url, PgConnection

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
    AND date_trunc('hour', c.ts) = date_trunc('hour', f.valid_for_ts)
    AND COALESCE(f.forecast_day, 0) = 0
WHERE c.temperature IS NOT NULL
  AND f.temperature IS NOT NULL
ORDER BY c.station_id, c.ts
"""


def main() -> None:
    dsn = get_database_url()

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)

    with PgConnection(dsn) as conn:
        # Quick sanity check
        clean_count = conn.execute("SELECT COUNT(*) FROM clean_telemetry").fetchone()[0]
        forecast_count = conn.execute("SELECT COUNT(*) FROM forecasts").fetchone()[0]
        print(f"Source rows — clean_telemetry: {clean_count}, forecasts: {forecast_count}")

        if clean_count == 0 or forecast_count == 0:
            print("ERROR: One or both source tables are empty. Run the pipeline first.")
            sys.exit(1)

        # Export via pandas (reads from psycopg2 connection)
        df = pd.read_sql(JOIN_QUERY, conn.raw)

    if df.empty:
        print("ERROR: JOIN produced 0 rows — no matching obs/forecast pairs yet.")
        sys.exit(1)

    df.to_parquet(OUT_PATH, index=False)

    file_size_kb = os.path.getsize(OUT_PATH) / 1024
    print(f"Exported {len(df)} rows, {len(df.columns)} columns to {OUT_PATH}")
    print(f"Columns: {', '.join(df.columns)}")
    print(f"File size: {file_size_kb:.1f} KB")


if __name__ == "__main__":
    main()
