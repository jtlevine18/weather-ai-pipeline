"""
Pydantic v2 data contracts for each pipeline stage.

Each model mirrors a DuckDB table schema from src/database.py.
Used for validation at stage boundaries — data flows as dicts internally,
but is validated through these models before passing between stages.
"""

from __future__ import annotations
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class RawReading(BaseModel):
    """Stage 1 output: sensor reading (real IMD / imdlib / synthetic), possibly with faults."""
    id: str
    station_id: str
    ts: str  # ISO timestamp string
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    wind_speed: Optional[float] = None
    wind_dir: Optional[float] = None
    pressure: Optional[float] = None
    rainfall: Optional[float] = None
    fault_type: Optional[str] = None
    source: str = "synthetic"


class CleanReading(BaseModel):
    """Stage 2 output: healed reading with quality metadata."""
    id: str
    station_id: str
    ts: str
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    wind_speed: Optional[float] = None
    wind_dir: Optional[float] = None
    pressure: Optional[float] = None
    rainfall: Optional[float] = None
    heal_action: str = "none"
    heal_source: str = "original"
    quality_score: float = Field(default=1.0, ge=0.0, le=1.0)


class Forecast(BaseModel):
    """Stage 3 output: MOS-corrected forecast."""
    id: str
    station_id: str
    issued_at: str
    valid_for_ts: str
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    wind_speed: Optional[float] = None
    rainfall: Optional[float] = None
    condition: str = "clear"
    model_used: str = "persistence"
    nwp_temp: Optional[float] = None
    correction: float = 0.0
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)


class DownscaledForecast(Forecast):
    """Stage 4 output: forecast adjusted to farmer GPS coordinates."""
    farmer_lat: Optional[float] = None
    farmer_lon: Optional[float] = None
    downscaled: bool = False
    idw_temp: Optional[float] = None
    lapse_delta: Optional[float] = None
    alt_delta_m: Optional[float] = None


class Advisory(BaseModel):
    """Stage 5 output: bilingual agricultural advisory."""
    id: str
    station_id: str
    farmer_lat: Optional[float] = None
    farmer_lon: Optional[float] = None
    issued_at: str
    condition: Optional[str] = None
    temperature: Optional[float] = None
    rainfall: Optional[float] = None
    advisory_en: Optional[str] = None
    advisory_local: Optional[str] = None
    language: str = "en"
    provider: str = "unknown"
    retrieval_docs: int = 0


class DeliveryLog(BaseModel):
    """Stage 6 output: delivery record."""
    id: str
    alert_id: Optional[str] = None
    station_id: Optional[str] = None
    channel: str
    recipient: str
    status: str = "sent"
    message: str = ""
