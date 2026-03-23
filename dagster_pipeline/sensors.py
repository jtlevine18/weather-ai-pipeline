"""
Sensors — event-driven triggers that watch for data changes and kick off
downstream asset materializations automatically.
"""

from datetime import datetime, timedelta, timezone

import duckdb
from dagster import (
    sensor,
    SensorEvaluationContext,
    RunRequest,
    SkipReason,
    AssetSelection,
)


@sensor(minimum_interval_seconds=60)
def forecast_complete_sensor(context: SensorEvaluationContext):
    """Check if the forecasts table was updated in the last 5 minutes.

    When fresh forecast rows exist, trigger a run that materializes only
    the downstream agricultural_alerts and delivery_log assets.
    """
    try:
        con = duckdb.connect("weather.duckdb", read_only=True)
        result = con.execute("SELECT MAX(issued_at) FROM forecasts").fetchone()
        con.close()
    except Exception as e:
        return SkipReason(f"Could not query forecasts table: {e}")

    if result is None or result[0] is None:
        return SkipReason("No rows in forecasts table yet.")

    latest_ts = result[0]
    # Normalise to a timezone-aware datetime for comparison
    if isinstance(latest_ts, str):
        latest_ts = datetime.fromisoformat(latest_ts)
    if latest_ts.tzinfo is None:
        latest_ts = latest_ts.replace(tzinfo=timezone.utc)

    threshold = datetime.now(timezone.utc) - timedelta(minutes=5)

    if latest_ts >= threshold:
        context.log.info(
            f"Forecasts updated at {latest_ts}. Triggering downstream assets."
        )
        return RunRequest(
            run_key=f"forecast-complete-{latest_ts.isoformat()}",
            asset_selection=AssetSelection.assets("agricultural_alerts", "delivery_log"),
        )

    return SkipReason(
        f"Latest forecast timestamp ({latest_ts}) is older than 5 minutes."
    )
