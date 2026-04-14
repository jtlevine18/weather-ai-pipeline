"""
Step 1: Ingestion — station-level weather data from configurable sources.

Default (India): IMD scraper → imdlib gridded. If both upstream sources
fail for a station, the reading is marked source="error" with NULL values
— no synthetic fallback. The explicit ingestion_source="synthetic" mode
is still available for testing.
Custom: set ingestion_source="custom" and provide a custom_ingest_fn in
WeatherDataConfig, or register a module that implements fetch_reading().

Provider interface
------------------
A custom ingestion function receives a StationConfig and returns a dict::

    async def my_fetch(station: StationConfig) -> dict:
        return {
            "temperature": 28.5,   # °C
            "humidity":    75.0,   # %
            "wind_speed":  8.2,    # km/h
            "pressure":    1012.0, # hPa
            "rainfall":    0.0,    # mm
        }

Set config.weather.ingestion_source = "custom" and
config.weather.custom_ingest_fn = my_fetch to use it.
"""

from __future__ import annotations
import asyncio
import importlib
import random
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from config import FaultInjectionConfig, PipelineConfig, STATIONS, StationConfig
from src.database import insert_raw_telemetry


# ---------------------------------------------------------------------------
# Realistic baseline ranges by region / season (synthetic generator)
# ---------------------------------------------------------------------------

def _baseline(station: StationConfig) -> Dict[str, float]:
    """Generate a realistic baseline reading for a station."""
    hour = datetime.now(timezone.utc).hour
    # Diurnal temperature cycle
    diurnal = 3.0 * (1.0 - abs(hour - 14) / 14.0)

    # Regional base temps
    if station.state == "Kerala":
        if station.altitude_m > 500:           # highland
            base_temp = 18.0 + diurnal
            base_rh   = 85.0
        elif station.altitude_m > 50:          # midland
            base_temp = 27.0 + diurnal
            base_rh   = 80.0
        else:                                  # coastal
            base_temp = 29.0 + diurnal
            base_rh   = 78.0
    else:                                      # Tamil Nadu
        if station.altitude_m > 300:           # western ghats
            base_temp = 24.0 + diurnal
            base_rh   = 65.0
        else:
            base_temp = 31.0 + diurnal
            base_rh   = 60.0

    return {
        "temperature": base_temp + random.gauss(0, 0.5),
        "humidity":    min(100.0, max(20.0, base_rh + random.gauss(0, 2.0))),
        "wind_speed":  max(0.0, random.gauss(8.0, 2.0)),
        "wind_dir":    random.uniform(0, 360),
        "pressure":    1013.25 - station.altitude_m * 0.12 + random.gauss(0, 1.5),
        "rainfall":    max(0.0, random.gauss(0.5, 1.0)),
    }


# ---------------------------------------------------------------------------
# Fault injection
# ---------------------------------------------------------------------------

def _inject_fault(reading: Dict[str, Any],
                  fault_cfg: FaultInjectionConfig) -> Dict[str, Any]:
    """Randomly introduce one of four fault types."""
    r = random.random()
    cumulative = 0.0

    # Typo — decimal shift on temperature
    cumulative += fault_cfg.typo_rate
    if r < cumulative:
        reading["temperature"] = reading["temperature"] * 10  # e.g., 29 → 290
        reading["fault_type"]  = "typo"
        return reading

    # Offline — clear all fields
    cumulative += fault_cfg.offline_rate
    if r < cumulative:
        reading["temperature"] = None
        reading["humidity"]    = None
        reading["wind_speed"]  = None
        reading["pressure"]    = None
        reading["rainfall"]    = None
        reading["fault_type"]  = "offline"
        return reading

    # Sensor drift — systematic offset
    cumulative += fault_cfg.drift_rate
    if r < cumulative:
        reading["temperature"] = (reading["temperature"] or 0) + 5.0
        reading["humidity"]    = min(100, (reading["humidity"] or 0) + 15.0)
        reading["fault_type"]  = "drift"
        return reading

    # Missing field
    cumulative += fault_cfg.missing_rate
    if r < cumulative:
        field = random.choice(["pressure", "rainfall", "wind_dir"])
        reading[field]        = None
        reading["fault_type"] = "missing_field"
        return reading

    reading["fault_type"] = None
    return reading


# ---------------------------------------------------------------------------
# Synthetic reading generator (original, preserved for fallback + tests)
# ---------------------------------------------------------------------------

def generate_synthetic_reading(station: StationConfig,
                                 fault_config: FaultInjectionConfig) -> Dict[str, Any]:
    reading = _baseline(station)
    reading["id"]         = f"{station.station_id}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}"
    reading["station_id"] = station.station_id
    reading["ts"]         = datetime.now(timezone.utc).isoformat()
    reading["source"]     = "synthetic"
    reading["fault_type"] = None
    reading = _inject_fault(reading, fault_config)
    return reading


# ---------------------------------------------------------------------------
# Real data fetching (IMD scraper → imdlib → synthetic fallback)
# ---------------------------------------------------------------------------

async def _fetch_real_reading(
    station: StationConfig,
    imd_client,
    imdlib_client,
) -> Dict[str, Any]:
    """Fetch real weather data for a station with three-tier fallback.

    Returns a reading dict matching the raw_telemetry schema.
    """
    now = datetime.now(timezone.utc)
    reading = {
        "id":         f"{station.station_id}_{now.strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}",
        "station_id": station.station_id,
        "ts":         now.isoformat(),
        "temperature": None,
        "humidity":    None,
        "wind_speed":  None,
        "wind_dir":    None,
        "pressure":    None,
        "rainfall":    None,
        "fault_type":  None,
        "source":      None,
    }

    # Tier 1: IMD scraper (temp + humidity + rainfall)
    imd_data = await imd_client.get_current(station.imd_id)
    if imd_data:
        reading["temperature"] = imd_data.get("temperature")
        reading["humidity"]    = imd_data.get("humidity")
        reading["rainfall"]    = imd_data.get("rainfall")
        reading["source"]      = "imd"
        return reading

    # Tier 2: imdlib gridded (temp + rainfall, no humidity)
    imdlib_data = await imdlib_client.get_current(station.lat, station.lon)
    if imdlib_data:
        reading["temperature"] = imdlib_data.get("temperature")
        reading["rainfall"]    = imdlib_data.get("rainfall")
        reading["source"]      = "imdlib"
        return reading

    # No synthetic fill: surface the gap so quality checks can flag it instead of masking with noise.
    reading["source"]     = "error"
    reading["fault_type"] = "upstream_fetch_failed"
    return reading


async def ingest_real_stations(config: PipelineConfig, conn) -> List[Dict[str, Any]]:
    """Fetch real weather data for all 20 stations and store in raw_telemetry."""
    from src.weather_clients import IMDClient, IMDLibClient

    imd_client   = IMDClient(cache_ttl_s=config.weather.imd_cache_ttl_s)
    imdlib_client = IMDLibClient()

    sem = asyncio.Semaphore(5)

    async def _fetch_one(station: StationConfig) -> Dict[str, Any]:
        async with sem:
            return await _fetch_real_reading(station, imd_client, imdlib_client)

    readings = await asyncio.gather(*[_fetch_one(s) for s in STATIONS])
    readings = list(readings)
    insert_raw_telemetry(conn, readings)
    return readings


# ---------------------------------------------------------------------------
# Public API — dispatcher
# ---------------------------------------------------------------------------

async def ingest_custom_stations(config: PipelineConfig, conn) -> List[Dict[str, Any]]:
    """Ingest weather data using a user-provided fetch function.

    Set config.weather.custom_ingest_fn to an async function that accepts a
    StationConfig and returns a dict with keys: temperature, humidity,
    wind_speed, pressure, rainfall.
    """
    fetch_fn = config.weather.custom_ingest_fn
    if fetch_fn is None:
        raise ValueError(
            "ingestion_source='custom' requires config.weather.custom_ingest_fn "
            "to be set to an async function(StationConfig) → dict. "
            "See src/ingestion.py docstring for the provider interface."
        )

    sem = asyncio.Semaphore(5)

    async def _fetch_one(station: StationConfig) -> Dict[str, Any]:
        async with sem:
            raw = await fetch_fn(station)
            now = datetime.now(timezone.utc)
            return {
                "id": f"{station.station_id}_{now.strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}",
                "station_id": station.station_id,
                "timestamp": now.isoformat(),
                "temperature": raw.get("temperature"),
                "humidity": raw.get("humidity"),
                "wind_speed": raw.get("wind_speed"),
                "pressure": raw.get("pressure"),
                "rainfall": raw.get("rainfall"),
                "source": "custom",
                "fault_type": None,
            }

    readings = await asyncio.gather(*[_fetch_one(s) for s in STATIONS])
    readings = list(readings)
    insert_raw_telemetry(conn, readings)
    return readings


async def ingest_all_stations(config: PipelineConfig, conn) -> List[Dict[str, Any]]:
    """Ingest weather readings — real, synthetic, or custom based on config.

    ingestion_source values:
      "real"      — IMD scraper + imdlib + synthetic fallback (India-specific)
      "synthetic" — generated data with configurable fault injection
      "custom"    — user-provided fetch function (see module docstring)
    """
    if config.weather.ingestion_source == "real":
        return await ingest_real_stations(config, conn)

    if config.weather.ingestion_source == "custom":
        return await ingest_custom_stations(config, conn)

    # Original synthetic path
    readings = []
    for station in STATIONS:
        rec = generate_synthetic_reading(station, config.weather.fault_config)
        readings.append(rec)
    insert_raw_telemetry(conn, readings)
    return readings
