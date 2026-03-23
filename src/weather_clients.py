"""
External weather API clients.
Each client has ONE job in the pipeline:
  - IMDClient          → Step 1 Ingest  (real station observations via JSON API)
  - IMDLibClient       → Step 1 Ingest  (gridded daily backup via imdlib)
  - TomorrowIOClient   → Step 2 Heal    (cross-validation reference)
  - OpenMeteoClient    → Step 3 Forecast (NWP baseline)
  - NASAPowerClient    → Step 4 Downscale (spatial grid)
"""

from __future__ import annotations
import asyncio
import logging
import re
import tempfile
import time
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import httpx

log = logging.getLogger(__name__)

IMD_API_BASE     = "https://city.imd.gov.in/citywx/responsive/api/fetchCity_static.php"
TOMORROW_IO_BASE = "https://api.tomorrow.io/v4"
OPEN_METEO_BASE  = "https://api.open-meteo.com/v1"
NASA_POWER_BASE  = "https://power.larc.nasa.gov/api/temporal/daily/point"

_TIMEOUT = httpx.Timeout(30.0)


# ---------------------------------------------------------------------------
# IMD JSON API — Step 1 (Real station observations)
# ---------------------------------------------------------------------------

class IMDClient:
    """Fetch current weather from IMD's JSON API for Indian SYNOP stations."""

    MISSING = 999.0  # IMD uses 999 as missing-data sentinel

    def __init__(self, cache_ttl_s: int = 1800):
        self._cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
        self._cache_ttl = cache_ttl_s

    async def get_current(self, imd_id: str) -> Optional[Dict[str, Any]]:
        """Fetch current temp/humidity/rainfall from IMD city weather API.

        Uses the JSON endpoint at city.imd.gov.in/citywx/responsive/api/.
        Returns dict with temperature, humidity, rainfall, source='imd'
        or None on failure.
        """
        if not imd_id:
            return None

        # Check cache
        if imd_id in self._cache:
            cached_time, cached_data = self._cache[imd_id]
            if time.time() - cached_time < self._cache_ttl:
                log.debug("IMD cache hit for %s", imd_id)
                return cached_data

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT, verify=False) as client:
                resp = await client.post(
                    IMD_API_BASE,
                    data={"ID": imd_id},
                )
                resp.raise_for_status()
                payload = resp.json()

            # API returns {"status": 404, "error": "..."} when no data
            if isinstance(payload, dict) and payload.get("status") == 404:
                log.info("IMD API: no data for station %s", imd_id)
                return None

            # Successful response is a list with one dict
            if isinstance(payload, list) and len(payload) > 0:
                return self._parse_json(payload[0], imd_id)

            log.warning("IMD API unexpected response for %s: %s", imd_id, type(payload))
            return None

        except Exception as exc:
            log.warning("IMD API error for station %s: %s", imd_id, exc)
            return None

    def _parse_json(self, row: Dict[str, Any], imd_id: str) -> Optional[Dict[str, Any]]:
        """Extract weather fields from IMD API JSON response."""
        data: Dict[str, Any] = {"source": "imd"}

        max_temp = self._safe_float(row.get("max"))
        min_temp = self._safe_float(row.get("min"))

        if max_temp is not None and min_temp is not None:
            data["temperature"] = round((max_temp + min_temp) / 2, 1)
        elif max_temp is not None:
            data["temperature"] = max_temp
        elif min_temp is not None:
            data["temperature"] = min_temp

        # Humidity (08:30 morning / 17:30 evening) — 999 = missing
        rh_am = self._safe_float(row.get("rh0830"))
        rh_pm = self._safe_float(row.get("rh1730"))

        if rh_am is not None and rh_pm is not None:
            data["humidity"] = round((rh_am + rh_pm) / 2, 1)
        elif rh_am is not None:
            data["humidity"] = rh_am
        elif rh_pm is not None:
            data["humidity"] = rh_pm

        rainfall = self._safe_float(row.get("rainfall"))
        if rainfall is not None:
            data["rainfall"] = rainfall

        # Must have at least temperature to be useful
        if "temperature" not in data:
            log.warning("IMD API: no temperature for station %s", imd_id)
            return None

        self._cache[imd_id] = (time.time(), data)
        return data

    def _safe_float(self, val: Any) -> Optional[float]:
        """Convert to float, treating None and 999 sentinel as missing."""
        if val is None:
            return None
        try:
            f = float(val)
            return None if abs(f) >= self.MISSING else f
        except (ValueError, TypeError):
            return None


# ---------------------------------------------------------------------------
# IMDLib — Step 1 backup (gridded daily data)
# ---------------------------------------------------------------------------

class IMDLibClient:
    """Fetch gridded daily data from IMD via imdlib as backup source."""

    MISSING = -999.0

    async def get_current(self, lat: float, lon: float) -> Optional[Dict[str, Any]]:
        """Fetch yesterday's gridded temp + rainfall for nearest grid cell.

        Returns dict with temperature (avg of tmin/tmax), rainfall,
        source='imdlib', or None on failure.
        """
        # imdlib is synchronous and does disk I/O; run in executor
        loop = asyncio.get_event_loop()
        try:
            return await loop.run_in_executor(None, self._fetch_sync, lat, lon)
        except Exception as exc:
            log.warning("IMDLib error at (%s,%s): %s", lat, lon, exc)
            return None

    def _fetch_sync(self, lat: float, lon: float) -> Optional[Dict[str, Any]]:
        """Synchronous fetch + extract from imdlib gridded data."""
        import imdlib as imd

        # Try yesterday first, then day-before-yesterday
        for days_back in (1, 2):
            target = date.today() - timedelta(days=days_back)
            date_str = target.strftime("%Y-%m-%d")

            try:
                with tempfile.TemporaryDirectory() as tmpdir:
                    result: Dict[str, Any] = {"source": "imdlib", "date": date_str}

                    # Fetch rainfall (0.25° grid)
                    try:
                        rain_data = imd.get_real_data("rain", date_str, date_str,
                                                       file_dir=tmpdir)
                        rain_xr = rain_data.get_xarray()
                        rain_val = float(rain_xr.sel(lat=lat, lon=lon, method="nearest")
                                         ["rain"].values[0])
                        if rain_val != self.MISSING:
                            result["rainfall"] = round(rain_val, 2)
                    except Exception as exc:
                        log.debug("IMDLib rain fetch failed for %s: %s", date_str, exc)

                    # Fetch tmax (0.5° grid)
                    tmax_val = None
                    try:
                        tmax_data = imd.get_real_data("tmax", date_str, date_str,
                                                       file_dir=tmpdir)
                        tmax_xr = tmax_data.get_xarray()
                        tmax_val = float(tmax_xr.sel(lat=lat, lon=lon, method="nearest")
                                         ["tmax"].values[0])
                        if tmax_val == self.MISSING:
                            tmax_val = None
                    except Exception as exc:
                        log.debug("IMDLib tmax fetch failed for %s: %s", date_str, exc)

                    # Fetch tmin (0.5° grid)
                    tmin_val = None
                    try:
                        tmin_data = imd.get_real_data("tmin", date_str, date_str,
                                                       file_dir=tmpdir)
                        tmin_xr = tmin_data.get_xarray()
                        tmin_val = float(tmin_xr.sel(lat=lat, lon=lon, method="nearest")
                                         ["tmin"].values[0])
                        if tmin_val == self.MISSING:
                            tmin_val = None
                    except Exception as exc:
                        log.debug("IMDLib tmin fetch failed for %s: %s", date_str, exc)

                    # Compute average temperature
                    if tmax_val is not None and tmin_val is not None:
                        result["temperature"] = round((tmax_val + tmin_val) / 2, 1)
                    elif tmax_val is not None:
                        result["temperature"] = round(tmax_val, 1)
                    elif tmin_val is not None:
                        result["temperature"] = round(tmin_val, 1)

                    # Must have at least temperature or rainfall
                    if "temperature" in result or "rainfall" in result:
                        return result

            except Exception as exc:
                log.debug("IMDLib fetch failed for %s (T-%d): %s", date_str, days_back, exc)
                continue

        return None


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
