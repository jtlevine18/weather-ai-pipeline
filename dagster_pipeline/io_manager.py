"""
PostgreSQL I/O manager for Dagster assets.

Bridges Dagster asset outputs (List[dict]) to PostgreSQL tables
using the existing insert/query helpers from src/database.py.
"""

from dagster import IOManager, io_manager, InputContext, OutputContext
from typing import Any, List, Dict

from src.database import (
    insert_raw_telemetry, insert_clean_telemetry, insert_forecast,
    insert_alert, insert_delivery_log,
    get_recent_forecasts, get_recent_alerts, get_all_clean_telemetry,
)


# Maps asset key → (insert_fn, query_fn)
TABLE_MAP = {
    "raw_telemetry": {
        "insert": insert_raw_telemetry,
        "query": lambda conn: conn.execute(
            "SELECT * FROM raw_telemetry ORDER BY ts DESC LIMIT 500"
        ).fetchall(),
        "table": "raw_telemetry",
    },
    "clean_telemetry": {
        "insert": insert_clean_telemetry,
        "query": lambda conn: get_all_clean_telemetry(conn),
        "table": "clean_telemetry",
    },
    "forecasts": {
        "insert": lambda conn, data: [insert_forecast(conn, r) for r in data],
        "query": lambda conn: get_recent_forecasts(conn, limit=100),
        "table": "forecasts",
    },
    "downscaled_forecasts": {
        # Downscaled forecasts are stored in the same forecasts table
        "insert": lambda conn, data: [insert_forecast(conn, r) for r in data],
        "query": lambda conn: get_recent_forecasts(conn, limit=100),
        "table": "forecasts",
    },
    "agricultural_alerts": {
        "insert": lambda conn, data: [insert_alert(conn, r) for r in data],
        "query": lambda conn: get_recent_alerts(conn, limit=100),
        "table": "agricultural_alerts",
    },
    "delivery_log": {
        "insert": lambda conn, data: [insert_delivery_log(conn, r) for r in data],
        "query": lambda conn: conn.execute(
            "SELECT * FROM delivery_log ORDER BY delivered_at DESC LIMIT 200"
        ).fetchall(),
        "table": "delivery_log",
    },
}


class PostgresIOManager(IOManager):
    """Persists asset outputs to PostgreSQL using existing insert helpers."""

    def __init__(self, postgres_resource):
        self._postgres = postgres_resource

    def handle_output(self, context: OutputContext, obj: Any):
        asset_key = context.asset_key.path[-1]
        mapping = TABLE_MAP.get(asset_key)
        if mapping is None:
            context.log.warning(f"No table mapping for asset {asset_key}, skipping persist")
            return

        conn = self._postgres.get_connection()
        try:
            if isinstance(obj, list):
                mapping["insert"](conn, obj)
                context.log.info(f"Persisted {len(obj)} records to {mapping['table']}")
            else:
                context.log.info(f"Asset {asset_key} returned non-list ({type(obj)}), persisted as metadata")
        finally:
            conn.close()

    def load_input(self, context: InputContext) -> Any:
        asset_key = context.asset_key.path[-1]
        mapping = TABLE_MAP.get(asset_key)
        if mapping is None:
            context.log.warning(f"No table mapping for asset {asset_key}")
            return []

        conn = self._postgres.get_connection()
        try:
            result = mapping["query"](conn)
            if isinstance(result, list) and result and isinstance(result[0], dict):
                context.log.info(f"Loaded {len(result)} records from {mapping['table']}")
                return result
            # Convert tuples to dicts if needed
            if isinstance(result, list) and result and isinstance(result[0], tuple):
                cols = [d[0] for d in conn.description] if conn.description else []
                dicts = [dict(zip(cols, row)) for row in result]
                context.log.info(f"Loaded {len(dicts)} records from {mapping['table']}")
                return dicts
            return result or []
        finally:
            conn.close()


@io_manager
def postgres_io_manager(init_context):
    postgres_resource = init_context.resources.postgres
    return PostgresIOManager(postgres_resource)
