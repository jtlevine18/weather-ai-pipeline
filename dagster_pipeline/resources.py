"""Dagster resources wrapping existing src/ clients.

Each resource holds configuration (API keys, paths) and provides
a method to get the underlying client from src/.
"""

from dagster import ConfigurableResource

from src.weather_clients import TomorrowIOClient, OpenMeteoClient, NASAPowerClient


class PostgresResource(ConfigurableResource):
    """Manages PostgreSQL connection lifecycle."""
    database_url: str = ""

    def get_connection(self):
        from src.database import init_db
        return init_db(self.database_url)


class TomorrowIOResource(ConfigurableResource):
    """Tomorrow.io API client for healing cross-validation."""
    api_key: str = ""

    def get_client(self) -> TomorrowIOClient:
        return TomorrowIOClient(self.api_key)


class OpenMeteoResource(ConfigurableResource):
    """Open-Meteo NWP forecast client."""

    def get_client(self) -> OpenMeteoClient:
        return OpenMeteoClient()


class NASAPowerResource(ConfigurableResource):
    """NASA POWER client for downscaling grids."""

    def get_client(self) -> NASAPowerClient:
        return NASAPowerClient()


class AnthropicResource(ConfigurableResource):
    """Anthropic API key for Claude advisory generation."""
    api_key: str = ""
