"""
NeuralGCM forecaster — Google DeepMind's neural weather model.

Runs the NeuralGCM 1.4° deterministic model on GPU (JAX) and extracts
station-level forecasts for all 20 IMD stations in a single inference pass.

Initial conditions: ERA5 reanalysis from Google's ARCO ERA5 Zarr archive
(free, no auth, ~5-day lag via ERA5T preliminary data).

Fallback chain: NeuralGCM (GPU) → Open-Meteo (free API) → Persistence model.

All heavy imports (neuralgcm, jax, xarray) are lazy so the rest of the
pipeline works fine on CPU-only machines without these packages installed.
"""

from __future__ import annotations
import logging
import math
import time as time_mod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class NeuralGCMResult:
    """Metadata from a NeuralGCM inference run."""
    model_name: str = ""
    init_time: str = ""
    forecast_hours: int = 24
    inference_time_s: float = 0.0
    data_fetch_time_s: float = 0.0
    stations_extracted: int = 0
    grid_shape: str = ""


# ---------------------------------------------------------------------------
# ERA5 data paths (Google Cloud — anonymous access)
# ---------------------------------------------------------------------------

# Pressure-level data: 37 levels, hourly, 0.25° global
ERA5_PL_PATH = "gs://gcp-public-data-arco-era5/ar/full_37-1h-0p25deg-chunk-1.zarr-v3"
# Single-level data: hourly, 0.25° global (SST, sea ice for forcings)
ERA5_SL_PATH = "gs://gcp-public-data-arco-era5/ar/1h-0p25deg-chunk-1.zarr-v3"

# Variables NeuralGCM needs on pressure levels
PRESSURE_LEVEL_VARS = [
    "u_component_of_wind",
    "v_component_of_wind",
    "temperature",
    "geopotential",
    "specific_humidity",
    "specific_cloud_ice_water_content",
    "specific_cloud_liquid_water_content",
]

# Surface forcing variables
FORCING_VARS = [
    "sea_surface_temperature",
    "sea_ice_cover",
]

# Model checkpoint paths on Google Cloud Storage
CHECKPOINT_BASE = "gs://neuralgcm/models/v1"


# ---------------------------------------------------------------------------
# Unit conversion helpers
# ---------------------------------------------------------------------------

def _specific_humidity_to_rh(q_kg_kg: float, temp_c: float, pressure_hpa: float) -> float:
    """Convert specific humidity (kg/kg) to relative humidity (%).

    Uses the Magnus formula for saturation vapor pressure.
    """
    if temp_c < -40 or q_kg_kg <= 0:
        return 0.0
    # Saturation vapor pressure (hPa)
    es = 6.112 * math.exp(17.67 * temp_c / (temp_c + 243.5))
    # Mixing ratio from specific humidity
    w = q_kg_kg / (1.0 - q_kg_kg)
    # Saturation mixing ratio
    ws = 0.622 * es / (pressure_hpa - es) if pressure_hpa > es else 1.0
    rh = (w / ws) * 100.0 if ws > 0 else 0.0
    return max(0.0, min(100.0, rh))


def _uv_to_speed_dir(u: float, v: float) -> Tuple[float, float]:
    """Convert u,v wind components (m/s) to speed (km/h) and direction (degrees).

    Meteorological convention: direction is where wind comes FROM.
    """
    speed_ms = math.sqrt(u ** 2 + v ** 2)
    speed_kmh = speed_ms * 3.6
    # Meteorological wind direction (from)
    direction = (270.0 - math.degrees(math.atan2(v, u))) % 360.0
    return round(speed_kmh, 1), round(direction, 1)


def _surface_pressure_from_altitude(altitude_m: float) -> float:
    """Estimate surface pressure (hPa) from station altitude using barometric formula."""
    # Standard atmosphere: P = P0 * (1 - L*h/T0)^(g*M/(R*L))
    # P0=1013.25, L=0.0065 K/m, T0=288.15 K, g=9.80665, M=0.0289644, R=8.31447
    if altitude_m <= 0:
        return 1013.25
    return 1013.25 * (1.0 - 0.0065 * altitude_m / 288.15) ** 5.2561


def _best_pressure_level(altitude_m: float) -> int:
    """Select the pressure level closest to station's surface pressure.

    Avoids extracting data from below-ground pressure levels for
    elevated stations (e.g., Coimbatore at 396m ≈ 960 hPa).
    """
    surface_p = _surface_pressure_from_altitude(altitude_m)
    # Standard pressure levels in ERA5 (subset near surface)
    candidates = [1000, 975, 950, 925, 900, 875, 850]
    # Pick the level closest to (but not exceeding) surface pressure
    best = 1000
    for level in candidates:
        if level <= surface_p + 10:  # allow small tolerance
            best = level
            break
    return best


# ---------------------------------------------------------------------------
# NeuralGCM Client
# ---------------------------------------------------------------------------

class NeuralGCMClient:
    """Runs NeuralGCM inference on GPU and extracts station-level forecasts.

    Usage:
        client = NeuralGCMClient()
        forecasts, meta = await client.get_forecasts_batch(stations)
        # forecasts: Dict[station_id, List[Dict]]  — same format as OpenMeteoClient
        # meta: NeuralGCMResult with inference stats
    """

    def __init__(
        self,
        model_name: str = "deterministic_1_4_deg",
        forecast_hours: int = 24,
    ):
        self.model_name = model_name
        self.forecast_hours = forecast_hours
        self._model = None
        self._gcs = None

    # ------------------------------------------------------------------
    # Lazy loading
    # ------------------------------------------------------------------

    def _get_gcs(self):
        """Lazy-init GCS filesystem (anonymous, for public buckets)."""
        if self._gcs is None:
            import gcsfs
            self._gcs = gcsfs.GCSFileSystem(token="anon")
        return self._gcs

    def _ensure_model(self):
        """Load NeuralGCM checkpoint from GCS (cached after first load)."""
        if self._model is not None:
            return

        import neuralgcm
        import pickle

        gcs = self._get_gcs()
        ckpt_path = f"{CHECKPOINT_BASE}/{self.model_name}.pkl"
        log.info("Loading NeuralGCM checkpoint: %s", ckpt_path)

        t0 = time_mod.time()
        with gcs.open(ckpt_path, "rb") as f:
            ckpt = pickle.load(f)
        self._model = neuralgcm.PressureLevelModel.from_checkpoint(ckpt)
        log.info("NeuralGCM model loaded in %.1fs", time_mod.time() - t0)

    # ------------------------------------------------------------------
    # ERA5 initial conditions
    # ------------------------------------------------------------------

    def _fetch_era5_sync(self) -> Tuple[Any, Any]:
        """Fetch latest ERA5 initial conditions from ARCO Zarr (synchronous).

        Returns (merged_xr_dataset, init_time_np64).
        """
        import xarray as xr
        import numpy as np

        gcs = self._get_gcs()

        log.info("Opening ARCO ERA5 pressure-level Zarr...")
        pl_store = gcs.get_mapper(ERA5_PL_PATH)
        pl_ds = xr.open_zarr(pl_store, consolidated=False)

        # Find latest available timestep
        latest_time = pl_ds.time[-1].values
        log.info("Latest ERA5 time available: %s", latest_time)

        # Select single timestep + required variables
        log.info("Fetching pressure-level data (%d vars × 37 levels)...",
                 len(PRESSURE_LEVEL_VARS))
        # Only fetch variables that exist in the dataset
        available_pl = [v for v in PRESSURE_LEVEL_VARS if v in pl_ds]
        if len(available_pl) < 4:
            raise ValueError(
                f"ARCO ERA5 missing critical variables. Found: {available_pl}"
            )
        pl_data = pl_ds[available_pl].sel(time=latest_time).compute()

        # Fetch surface forcings (SST, sea ice)
        log.info("Fetching surface forcings...")
        sl_store = gcs.get_mapper(ERA5_SL_PATH)
        sl_ds = xr.open_zarr(sl_store, consolidated=False)
        available_sl = [v for v in FORCING_VARS if v in sl_ds]
        if available_sl:
            sl_data = sl_ds[available_sl].sel(
                time=latest_time, method="nearest"
            ).compute()
            # Fill NaN in SST (undefined over land) with nearest-neighbor
            for var in available_sl:
                if sl_data[var].isnull().any():
                    # Simple fill: use global mean where NaN
                    mean_val = float(sl_data[var].mean(skipna=True).values)
                    sl_data[var] = sl_data[var].fillna(mean_val)
            merged = xr.merge([pl_data, sl_data])
        else:
            log.warning("No forcing variables found in single-level dataset")
            merged = pl_data

        return merged, latest_time

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def _run_inference_sync(self, init_ds, init_time) -> Any:
        """Run NeuralGCM forecast from initial conditions (synchronous, GPU).

        Returns xarray Dataset with forecast output on model grid.
        """
        import jax
        import numpy as np

        model = self._model

        log.info("Encoding initial state...")
        inputs = model.inputs_from_xarray(init_ds)
        forcings = model.forcings_from_xarray(init_ds)

        rng_key = jax.random.key(42)
        initial_state = model.encode(inputs, forcings, rng_key)

        # Forecast configuration: output every 6 hours
        inner_steps = 6
        outer_steps = max(1, self.forecast_hours // inner_steps)
        timedelta = np.timedelta64(inner_steps, "h")

        log.info(
            "Running NeuralGCM: %d steps × %dh = %dh forecast...",
            outer_steps, inner_steps, outer_steps * inner_steps,
        )

        t0 = time_mod.time()
        final_state, predictions = model.unroll(
            initial_state,
            forcings,      # persistent forcings (SST stable over 24h)
            steps=outer_steps,
            timedelta=timedelta,
            start_with_input=True,
        )
        inference_s = time_mod.time() - t0
        log.info("NeuralGCM inference completed in %.1fs", inference_s)

        # Convert JAX arrays back to xarray
        times = [
            init_time + np.timedelta64(i * inner_steps, "h")
            for i in range(outer_steps + 1)
        ]
        output_ds = model.data_to_xarray(predictions, times=times)

        return output_ds, inference_s

    # ------------------------------------------------------------------
    # Station extraction
    # ------------------------------------------------------------------

    def _extract_station_forecasts(
        self,
        output_ds,
        stations: List,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Extract surface weather variables at each station from NeuralGCM output grid.

        For each station, selects the nearest grid point and extracts:
        temperature, humidity, wind speed/dir, pressure, rainfall.

        Returns Dict[station_id, List[Dict]] — same format as OpenMeteoClient.
        """
        import numpy as np

        results: Dict[str, List[Dict[str, Any]]] = {}

        # Determine coordinate names (NeuralGCM might use 'lat'/'lon' or 'latitude'/'longitude')
        lat_name = "latitude" if "latitude" in output_ds.dims else "lat"
        lon_name = "longitude" if "longitude" in output_ds.dims else "lon"
        level_name = "level" if "level" in output_ds.dims else "pressure_level"

        # Check available output variables
        has_temp = "temperature" in output_ds
        has_q = "specific_humidity" in output_ds
        has_u = "u_component_of_wind" in output_ds
        has_v = "v_component_of_wind" in output_ds
        has_precip = any(
            v in output_ds
            for v in ("total_precipitation", "precipitation", "precipitation_rate")
        )
        precip_var = next(
            (v for v in ("total_precipitation", "precipitation", "precipitation_rate")
             if v in output_ds),
            None,
        )

        # Determine longitude convention (0-360 or -180-180)
        lon_values = output_ds[lon_name].values
        uses_360 = float(lon_values.max()) > 180

        for station in stations:
            try:
                # Adjust longitude to match dataset convention
                stn_lon = station.lon
                if uses_360 and stn_lon < 0:
                    stn_lon += 360.0
                elif not uses_360 and stn_lon > 180:
                    stn_lon -= 360.0

                # Select nearest grid point
                point = output_ds.sel(
                    **{lat_name: station.lat, lon_name: stn_lon},
                    method="nearest",
                )

                # Best pressure level for this station's altitude
                target_level = _best_pressure_level(station.altitude_m)
                surface_p = _surface_pressure_from_altitude(station.altitude_m)

                forecasts = []
                n_times = len(point.time)
                for t_idx in range(n_times):
                    step = point.isel(time=t_idx)
                    ts_val = step.time.values
                    # Format timestamp as ISO string
                    ts_str = str(np.datetime_as_string(ts_val, unit="s")).replace("T", " ")

                    # Temperature (K → °C) at appropriate pressure level
                    temp_c = None
                    if has_temp:
                        try:
                            temp_k = float(
                                step["temperature"].sel(
                                    **{level_name: target_level}, method="nearest"
                                )
                            )
                            temp_c = round(temp_k - 273.15, 1)
                        except Exception:
                            pass

                    # Humidity (specific → relative)
                    rh = None
                    if has_q and temp_c is not None:
                        try:
                            q = float(
                                step["specific_humidity"].sel(
                                    **{level_name: target_level}, method="nearest"
                                )
                            )
                            rh = round(
                                _specific_humidity_to_rh(q, temp_c, float(target_level)),
                                1,
                            )
                        except Exception:
                            pass

                    # Wind (u,v → speed, direction)
                    wind_speed = None
                    wind_dir = None
                    if has_u and has_v:
                        try:
                            u = float(
                                step["u_component_of_wind"].sel(
                                    **{level_name: target_level}, method="nearest"
                                )
                            )
                            v = float(
                                step["v_component_of_wind"].sel(
                                    **{level_name: target_level}, method="nearest"
                                )
                            )
                            wind_speed, wind_dir = _uv_to_speed_dir(u, v)
                        except Exception:
                            pass

                    # Precipitation
                    rainfall = 0.0
                    if has_precip and precip_var:
                        try:
                            # Precipitation is a surface variable (no pressure level)
                            pval = float(step[precip_var])
                            # Convert m/s or kg/m²/s to mm/h if needed
                            if pval < 0.1:  # likely in m/s or kg/m²/s
                                pval *= 3600.0  # → mm/h
                            rainfall = round(max(0.0, pval), 1)
                        except Exception:
                            pass

                    forecasts.append({
                        "ts": ts_str,
                        "temperature": temp_c,
                        "humidity": rh,
                        "wind_speed": wind_speed,
                        "wind_dir": wind_dir,
                        "pressure": round(surface_p, 1),
                        "rainfall": rainfall,
                        "source": "neuralgcm",
                    })

                results[station.station_id] = forecasts

            except Exception as exc:
                log.warning(
                    "Failed to extract NeuralGCM forecast for %s: %s",
                    station.station_id, exc,
                )
                continue

        return results

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_forecasts_batch(
        self,
        stations: List,
    ) -> Tuple[Dict[str, List[Dict[str, Any]]], NeuralGCMResult]:
        """Run NeuralGCM and return forecasts for all stations.

        One inference pass covers all 20 stations (global model).

        Returns:
            forecasts: Dict[station_id, List[Dict]] — same format as OpenMeteoClient
            meta: NeuralGCMResult with inference stats
        """
        import asyncio

        meta = NeuralGCMResult(
            model_name=self.model_name,
            forecast_hours=self.forecast_hours,
        )

        loop = asyncio.get_event_loop()

        # Load model (first call downloads checkpoint from GCS, ~30s)
        self._ensure_model()

        # Fetch ERA5 initial conditions
        t0 = time_mod.time()
        init_ds, init_time = await loop.run_in_executor(
            None, self._fetch_era5_sync
        )
        meta.data_fetch_time_s = round(time_mod.time() - t0, 1)
        meta.init_time = str(init_time)

        # Run NeuralGCM inference on GPU
        output_ds, inference_s = await loop.run_in_executor(
            None, self._run_inference_sync, init_ds, init_time
        )
        meta.inference_time_s = round(inference_s, 1)

        # Log grid shape for debugging
        try:
            shape_parts = []
            for dim in output_ds.dims:
                shape_parts.append(f"{dim}={output_ds.dims[dim]}")
            meta.grid_shape = " × ".join(shape_parts)
        except Exception:
            pass

        # Extract station-level forecasts from global grid
        forecasts = self._extract_station_forecasts(output_ds, stations)
        meta.stations_extracted = len(forecasts)

        log.info(
            "NeuralGCM complete: %d stations, init=%s, inference=%.1fs, fetch=%.1fs",
            meta.stations_extracted, meta.init_time,
            meta.inference_time_s, meta.data_fetch_time_s,
        )

        return forecasts, meta


# ---------------------------------------------------------------------------
# Module-level availability check
# ---------------------------------------------------------------------------

def is_neuralgcm_available() -> bool:
    """Check if NeuralGCM and its dependencies (JAX, etc.) are installed."""
    missing = []
    for pkg in ("neuralgcm", "jax", "gcsfs", "xarray"):
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        log.warning("NeuralGCM unavailable — missing packages: %s", ", ".join(missing))
        return False
    return True


def get_neuralgcm_device() -> str:
    """Return the JAX device type (cpu/gpu/tpu) if available."""
    try:
        import jax
        devices = jax.devices()
        if devices:
            return str(devices[0].platform)
        return "unknown"
    except ImportError:
        return "not_installed"
