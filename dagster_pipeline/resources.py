"""
Dagster resources — thin wrappers around existing API clients and DB.

Each resource holds configuration (API keys, paths) and provides
a method to get the underlying client from src/.
"""

from dagster import ConfigurableResource
import duckdb

from src.weather_clients import TomorrowIOClient, OpenMeteoClient, NASAPowerClient
from src.database import init_db


class DuckDBResource(ConfigurableResource):
    """Manages DuckDB connection lifecycle."""
    db_path: str = "weather.duckdb"
    _ddl_done: bool = False

    class Config:
        arbitrary_types_allowed = True

    def get_connection(self) -> duckdb.DuckDBPyConnection:
        if not DuckDBResource._ddl_done:
            conn = init_db(self.db_path)
            DuckDBResource._ddl_done = True
            return conn
        return duckdb.connect(self.db_path)


class TomorrowIOResource(ConfigurableResource):
    """Tomorrow.io API client for healing cross-validation."""
    api_key: str = ""

    def get_client(self) -> TomorrowIOClient:
        return TomorrowIOClient(self.api_key)


class OpenMeteoResource(ConfigurableResource):
    """Open-Meteo NWP client for forecasting."""

    def get_client(self) -> OpenMeteoClient:
        return OpenMeteoClient()


class NASAPowerResource(ConfigurableResource):
    """NASA POWER client for downscaling grids."""

    def get_client(self) -> NASAPowerClient:
        return NASAPowerClient()


class AnthropicResource(ConfigurableResource):
    """Anthropic API key for Claude advisory generation."""
    api_key: str = ""
