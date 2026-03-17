"""
External weather API clients.
Each client has ONE job in the pipeline:
  - TomorrowIOClient  → Step 2 Heal  (cross-validation reference)
  - OpenMeteoClient   → Step 3 Forecast (NWP baseline)
  - NASAPowerClient   → Step 4 Downscale (spatial grid)
"""

from __future__ import annotations
import asyncio
import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import httpx

log = logging.getLogger(__name__)

TOMORROW_IO_BASE = "https://api.tomorrow.io/v4"
OPEN_METEO_BASE  = "https://api.open-meteo.com/v1"
NASA_POWER_BASE  = "https://power.larc.nasa.gov/api/temporal/daily/point"

_TIMEOUT = httpx.Timeout(30.0)


# ---------------------------------------------------------------------------
# Tomorrow.io — Step 2 (Healing reference)
# ---------------------------------------------------------------------------

class TomorrowIOClient:
    def __init__(self, api_key: str):
        self.api_key = api_key

    async def get_current(self, lat: float, lon: float) -> Optional[Dict[str, Any]]:
        """Return current realtime weather from Tomorrow.io."""
        if not self.api_key:
            log.warning("Tomorrow.io key not set — skipping")
            return None
        url = f"{TOMORROW_IO_BASE}/weather/realtime"
        params = {
            "location": f"{lat},{lon}",
            "apikey": self.api_key,
            "units": "metric",
            "fields": "temperature,humidity,windSpeed,windDirection,pressureSurfaceLevel,rainIntensity",
        }
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
            values = data["data"]["values"]
            return {
                "temperature": values.get("temperature"),
                "humidity":    values.get("humidity"),
                "wind_speed":  values.get("windSpeed"),
                "wind_dir":    values.get("windDirection"),
                "pressure":    values.get("pressureSurfaceLevel"),
                "rainfall":    values.get("rainIntensity", 0.0),
                "source":      "tomorrow_io",
            }
        except Exception as exc:
            log.warning("Tomorrow.io error at (%s,%s): %s", lat, lon, exc)
            return None


# ---------------------------------------------------------------------------
# Open-Meteo — Step 3 (NWP Forecast)
# ---------------------------------------------------------------------------

class OpenMeteoClient:
    async def get_forecast(self, lat: float, lon: float,
                            hours: int = 48) -> List[Dict[str, Any]]:
        """Return hourly NWP forecast from Open-Meteo (GFS/ECMWF)."""
        url = f"{OPEN_METEO_BASE}/forecast"
        params = {
            "latitude":  lat,
            "longitude": lon,
            "hourly":    "temperature_2m,relativehumidity_2m,windspeed_10m,winddirection_10m,surface_pressure,precipitation",
            "forecast_days": max(2, hours // 24 + 1),
            "timezone":  "Asia/Kolkata",
        }
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
            hourly = data.get("hourly", {})
            times = hourly.get("time", [])
            results = []
            for i, ts in enumerate(times[:hours]):
                results.append({
                    "ts":          ts,
                    "temperature": hourly["temperature_2m"][i],
                    "humidity":    hourly["relativehumidity_2m"][i],
                    "wind_speed":  hourly["windspeed_10m"][i],
                    "wind_dir":    hourly["winddirection_10m"][i],
                    "pressure":    hourly["surface_pressure"][i],
                    "rainfall":    hourly["precipitation"][i],
                    "source":      "open_meteo",
                })
            return results
        except Exception as exc:
            log.warning("Open-Meteo error at (%s,%s): %s", lat, lon, exc)
            return []


# ---------------------------------------------------------------------------
# NASA POWER — Step 4 (Downscaling grid) + healing fallback
# ---------------------------------------------------------------------------

class NASAPowerClient:
    NASA_MISSING = -999.0

    async def get_current(self, lat: float, lon: float) -> Optional[Dict[str, Any]]:
        """Fetch the most recent valid daily observation from NASA POWER."""
        # NASA POWER has a 2-3 day lag; fetch 7-day window
        end   = date.today() - timedelta(days=2)
        start = end - timedelta(days=7)
        params = {
            "parameters": "T2M,RH2M,WS10M,PS,PRECTOTCORR",
            "community":  "AG",
            "longitude":  lon,
            "latitude":   lat,
            "start":      start.strftime("%Y%m%d"),
            "end":        end.strftime("%Y%m%d"),
            "format":     "JSON",
        }
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(NASA_POWER_BASE, params=params)
                resp.raise_for_status()
                data = resp.json()
            props = data["properties"]["parameter"]
            # Find most recent date with valid T2M
            t2m = props.get("T2M", {})
            for day in sorted(t2m.keys(), reverse=True):
                temp = t2m[day]
                if temp != self.NASA_MISSING:
                    rh   = props.get("RH2M", {}).get(day, self.NASA_MISSING)
                    ws   = props.get("WS10M", {}).get(day, self.NASA_MISSING)
                    ps   = props.get("PS", {}).get(day, self.NASA_MISSING)
                    prec = props.get("PRECTOTCORR", {}).get(day, self.NASA_MISSING)
                    return {
                        "temperature": temp,
                        "humidity":    rh   if rh   != self.NASA_MISSING else None,
                        "wind_speed":  ws   if ws   != self.NASA_MISSING else None,
                        "pressure":    ps   if ps   != self.NASA_MISSING else None,
                        "rainfall":    prec if prec != self.NASA_MISSING else 0.0,
                        "source":      "nasa_power",
                        "date":        day,
                    }
            return None
        except Exception as exc:
            log.warning("NASA POWER error at (%s,%s): %s", lat, lon, exc)
            return None

    async def get_grid(self, lat: float, lon: float,
                        radius_deg: float = 0.5) -> List[Dict[str, Any]]:
        """Fetch a grid of ~25 cells around a station for IDW interpolation."""
        import numpy as np

        offsets = [-0.5, -0.25, 0.0, 0.25, 0.5]
        tasks = []
        coords = []
        for dlat in offsets:
            for dlon in offsets:
                coords.append((lat + dlat, lon + dlon))

        async def _fetch(lt, ln):
            return await self.get_current(lt, ln)

        results = await asyncio.gather(*[_fetch(lt, ln) for lt, ln in coords],
                                        return_exceptions=True)
        grid = []
        for (lt, ln), res in zip(coords, results):
            if isinstance(res, dict) and res is not None:
                res["lat"] = lt
                res["lon"] = ln
                grid.append(res)
        return grid
