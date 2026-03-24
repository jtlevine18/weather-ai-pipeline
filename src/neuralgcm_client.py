"""
NeuralGCM forecaster — Google DeepMind's neural weather model.

Runs the NeuralGCM 2.8° deterministic model on GPU (JAX) and extracts
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
    forecast_hours: int = 168
    inference_time_s: float = 0.0
    data_fetch_time_s: float = 0.0
    stations_extracted: int = 0
    grid_shape: str = ""


# ---------------------------------------------------------------------------
# ERA5 data path (Google Cloud — anonymous access)
# Both pressure-level and surface variables live in the same store.
# ---------------------------------------------------------------------------

ERA5_PATH = "gs://gcp-public-data-arco-era5/ar/full_37-1h-0p25deg-chunk-1.zarr-v3"

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
        model_name: str = "deterministic_2_8_deg",
        forecast_hours: int = 168,
    ):
        self.model_name = model_name
        self.forecast_hours = forecast_hours  # minimum forecast horizon beyond "now"
        self._model = None
        self._gcs = None
        self._init_time = None  # set after ERA5 fetch, used to compute total unroll

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

        # Set XLA memory flags before any JAX operation —
        # on-demand allocation instead of 90% upfront reservation
        import os
        os.environ.setdefault("XLA_PYTHON_CLIENT_PREALLOCATE", "false")
        os.environ.setdefault("XLA_PYTHON_CLIENT_MEM_FRACTION", "0.95")

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

        Both pressure-level and surface variables (SST, sea ice) live in the
        same store. We select only the variables the model needs via
        model.input_variables + model.forcing_variables.

        ERA5T (preliminary) data lags ~5 days; the store's time axis extends
        to 2050 but future slots are empty (all NaN). We search backwards
        from 5 days ago to find the most recent time with real data.

        Returns (xr_dataset, init_time_np64).
        """
        import xarray as xr
        import numpy as np

        gcs_opts = {"token": "anon"}
        model = self._model

        log.info("Opening ARCO ERA5 Zarr...")
        full_ds = xr.open_zarr(ERA5_PATH, chunks=None,
                               storage_options=gcs_opts, consolidated=True)

        # Select only the variables the model needs (pressure-level + forcings)
        all_vars = model.input_variables + model.forcing_variables
        available = [v for v in all_vars if v in full_ds]
        missing = [v for v in all_vars if v not in full_ds]
        if missing:
            log.warning("ERA5 store missing variables: %s", missing)
        if len(available) < 4:
            raise ValueError(f"ARCO ERA5 missing critical variables. Found: {available}")

        # Find latest time with actual data — the store extends to 2050 but
        # future time slots are all NaN. ERA5T lags ~5 days.
        # Try 5 days ago first, then 6, 7, 8 days ago as fallback.
        now = np.datetime64("now")
        test_var = available[0]  # check one pressure-level var
        init_time = None
        for lag_days in range(5, 12):
            candidate = now - np.timedelta64(lag_days * 24, "h")
            # Snap to nearest available hour in the store
            candidate = full_ds.time.sel(time=candidate, method="nearest").values
            probe = full_ds[test_var].sel(time=candidate).isel(level=0, latitude=360, longitude=720)
            val = float(probe.compute().values)
            if not np.isnan(val):
                init_time = candidate
                log.info("Found ERA5 data at lag=%d days, time=%s", lag_days, init_time)
                break
            log.info("ERA5 at lag=%d days (%s): NaN, trying older...", lag_days, candidate)

        if init_time is None:
            raise ValueError("No valid ERA5 data found in the last 12 days")

        log.info("Fetching %d variables at %s...", len(available), init_time)
        # Keep time dim as a length-1 slice (regridder and model expect it)
        data = full_ds[available].sel(time=slice(init_time, init_time)).compute()

        log.info("ERA5 data shape: %s, vars: %s",
                 {d: data.sizes[d] for d in data.dims}, list(data.data_vars))

        # Fill NaN in surface forcing variables (SST is NaN over land)
        # Must do this BEFORE regridding or the regridder propagates NaN
        for var in model.forcing_variables:
            if var in data and data[var].isnull().any():
                mean_val = float(data[var].mean(skipna=True).values)
                if np.isnan(mean_val):
                    log.warning("Variable %s is ALL NaN even at %s — filling with 0", var, init_time)
                    data[var] = data[var].fillna(0.0)
                else:
                    data[var] = data[var].fillna(mean_val)
                    log.info("Filled NaN in %s with global mean %.2f", var, mean_val)

        self._init_time = init_time
        return data, init_time

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def _run_inference_sync(self, init_ds, init_time) -> Any:
        """Run NeuralGCM forecast from initial conditions (synchronous, GPU).

        Returns xarray Dataset with forecast output on model grid.
        """
        import jax
        import numpy as np
        from dinosaur import spherical_harmonic, horizontal_interpolation
        from dinosaur import xarray_utils

        model = self._model

        # Regrid ERA5 (0.25°) to model's native grid using dinosaur
        # (same approach as official NeuralGCM inference demo)
        era5_grid = spherical_harmonic.Grid(
            latitude_nodes=init_ds.sizes["latitude"],
            longitude_nodes=init_ds.sizes["longitude"],
            latitude_spacing=xarray_utils.infer_latitude_spacing(init_ds.latitude),
            longitude_offset=xarray_utils.infer_longitude_offset(init_ds.longitude),
        )
        regridder = horizontal_interpolation.ConservativeRegridder(
            era5_grid, model.data_coords.horizontal, skipna=True,
        )
        log.info("Regridding ERA5 (%d×%d) → model grid (%d×%d), spacing=%s...",
                 era5_grid.longitude_nodes, era5_grid.latitude_nodes,
                 model.data_coords.horizontal.longitude_nodes,
                 model.data_coords.horizontal.latitude_nodes,
                 xarray_utils.infer_latitude_spacing(init_ds.latitude))
        init_ds = xarray_utils.regrid(init_ds, regridder)
        init_ds = xarray_utils.fill_nan_with_nearest(init_ds)

        # Log post-regrid state for debugging
        nan_vars = [v for v in init_ds.data_vars if init_ds[v].isnull().any()]
        log.info("Post-regrid: dims=%s, nan_vars=%s",
                 {d: init_ds.sizes[d] for d in init_ds.dims}, nan_vars)

        log.info("Encoding initial state...")
        inputs = model.inputs_from_xarray(init_ds.isel(time=0))
        forcings = model.forcings_from_xarray(init_ds.isel(time=0))

        rng_key = jax.random.key(42)
        initial_state = model.encode(inputs, forcings, rng_key)

        # Persistent forcings for unroll (SST/sea-ice from full time slice)
        all_forcings = model.forcings_from_xarray(init_ds.head(time=1))

        # Compute total forecast hours: must cover ERA5 lag + desired horizon.
        # ERA5 init is ~5 days old, so we unroll enough to reach now + forecast_hours.
        era5_age_h = max(0, int(
            (np.datetime64("now") - init_time) / np.timedelta64(1, "h")
        ))
        total_forecast_hours = era5_age_h + self.forecast_hours
        inner_steps = 6  # output every 6 hours
        total_steps = max(1, -(-total_forecast_hours // inner_steps))  # ceiling division
        timedelta = np.timedelta64(inner_steps, "h")

        # Chain short unrolls to avoid GPU OOM.
        # A single unroll of 28 steps stores all intermediate predictions (~66 GB).
        # Instead, run 4-step chunks: discard catch-up predictions, keep only the
        # final chunk that covers now → now + forecast_hours.
        chunk_size = 4  # 4-step chunks — ~16GB for 2.8° model, fits L40S (48GB) comfortably
        forecast_steps = max(1, -(-self.forecast_hours // inner_steps))  # steps for actual forecast
        catchup_steps = max(0, total_steps - forecast_steps)

        log.info(
            "NeuralGCM plan: ERA5 age=%dh | catch-up=%d steps, forecast=%d steps "
            "(chunks of %d) | total=%dh",
            era5_age_h, catchup_steps, forecast_steps, chunk_size,
            total_steps * inner_steps,
        )

        t0 = time_mod.time()
        state = initial_state

        # Phase 1: Catch-up — unroll to present, discard predictions to save memory
        steps_done = 0
        while steps_done < catchup_steps:
            n = min(chunk_size, catchup_steps - steps_done)
            state, _discarded = model.unroll(
                state, all_forcings, steps=n, timedelta=timedelta,
                start_with_input=(steps_done == 0),
            )
            steps_done += n
            elapsed_h = (steps_done) * inner_steps
            log.info("  Catch-up: %d/%d steps done (%dh / %dh)",
                     steps_done, catchup_steps, elapsed_h, catchup_steps * inner_steps)
            del _discarded  # free GPU memory

        # Phase 2: Forecast — convert each chunk to xarray immediately.
        # NeuralGCM's data_to_xarray() handles its own unroll output format,
        # but concatenating raw JAX predictions across chunks fails because
        # the pytree structure contains Python lists that break jnp.concatenate.
        # Solution: let data_to_xarray convert each chunk, then xr.concat.
        import xarray as xr

        forecast_start = init_time + np.timedelta64(catchup_steps * inner_steps, "h")
        chunk_datasets = []
        forecast_steps_done = 0
        while forecast_steps_done < forecast_steps:
            n = min(chunk_size, forecast_steps - forecast_steps_done)
            is_first = (forecast_steps_done == 0 and catchup_steps == 0)
            state, chunk_pred = model.unroll(
                state, all_forcings, steps=n, timedelta=timedelta,
                start_with_input=is_first,
            )

            # Convert this chunk to xarray immediately.
            # start_with_input=True → n+1 outputs (includes initial state)
            # start_with_input=False → n outputs (steps only)
            # Try both since behavior may vary by model version.
            chunk_start = forecast_start + np.timedelta64(forecast_steps_done * inner_steps, "h")
            chunk_ds = None
            for num_times, offset in [(n + 1, 0), (n, 1)]:
                try:
                    chunk_times = [
                        chunk_start + np.timedelta64((j + offset) * inner_steps, "h")
                        for j in range(num_times)
                    ]
                    chunk_ds = model.data_to_xarray(chunk_pred, times=chunk_times)
                    break
                except Exception as e:
                    log.debug("data_to_xarray with %d times failed: %s", num_times, e)
                    continue

            if chunk_ds is None:
                raise RuntimeError(
                    f"data_to_xarray failed for chunk at step {forecast_steps_done}, "
                    f"pred type={type(chunk_pred).__name__}"
                )

            chunk_datasets.append(chunk_ds)
            del chunk_pred  # free GPU memory

            forecast_steps_done += n
            log.info("  Forecast: %d/%d steps done (%dh / %dh)",
                     forecast_steps_done, forecast_steps,
                     forecast_steps_done * inner_steps, forecast_steps * inner_steps)

        inference_s = time_mod.time() - t0
        log.info("NeuralGCM inference completed in %.1fs", inference_s)

        # Concatenate xarray datasets (robust — no JAX tree manipulation)
        if len(chunk_datasets) == 1:
            output_ds = chunk_datasets[0]
        else:
            output_ds = xr.concat(chunk_datasets, dim="time")
            # Remove duplicate times at chunk boundaries
            _, unique_idx = np.unique(output_ds.time.values, return_index=True)
            output_ds = output_ds.isel(time=sorted(unique_idx))

        log.info("Output: %d timesteps from %s to %s",
                 output_ds.sizes["time"],
                 output_ds.time.values[0], output_ds.time.values[-1])

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
