"""
Step 1: Ingestion — synthetic weather data generator with configurable fault injection.
Simulates 20 ground sensors in Kerala and Tamil Nadu.
"""

from __future__ import annotations
import random
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from config import FaultInjectionConfig, PipelineConfig, STATIONS, StationConfig
from src.database import insert_raw_telemetry


# ---------------------------------------------------------------------------
# Realistic baseline ranges by region / season
# ---------------------------------------------------------------------------

def _baseline(station: StationConfig) -> Dict[str, float]:
    """Generate a realistic baseline reading for a station."""
    hour = datetime.utcnow().hour
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
# Public API
# ---------------------------------------------------------------------------

def generate_synthetic_reading(station: StationConfig,
                                 fault_config: FaultInjectionConfig) -> Dict[str, Any]:
    reading = _baseline(station)
    reading["id"]         = f"{station.station_id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}"
    reading["station_id"] = station.station_id
    reading["ts"]         = datetime.utcnow().isoformat()
    reading["source"]     = "synthetic"
    reading["fault_type"] = None
    reading = _inject_fault(reading, fault_config)
    return reading


async def ingest_all_stations(config: PipelineConfig, conn) -> List[Dict[str, Any]]:
    """Generate synthetic readings for all 20 stations and store in raw_telemetry."""
    readings = []
    for station in STATIONS:
        rec = generate_synthetic_reading(station, config.weather.fault_config)
        readings.append(rec)
    insert_raw_telemetry(conn, readings)
    return readings
