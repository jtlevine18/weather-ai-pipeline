"""
GraphCast forecaster — Google DeepMind's 0.25° graph neural network weather model.

Runs GraphCast_operational on GPU (JAX) and extracts station-level forecasts
for all 20 IMD stations in a single inference pass. Drop-in replacement for
NeuralGCMClient.

GraphCast_operational: 0.25° resolution, 13 pressure levels, fine-tuned on
HRES 2016-2021. Produces precipitation directly (no precip input needed).

Initial conditions: ERA5 reanalysis from Google's ARCO ERA5 Zarr archive
(same source as NeuralGCM — free, no auth, ~5-day lag via ERA5T).

Requires A100 80GB GPU. Falls back to NeuralGCM or Open-Meteo on smaller GPUs.

All heavy imports (graphcast, jax, xarray) are lazy so the rest of the
pipeline works fine on CPU-only machines without these packages installed.
"""

from __future__ import annotations
import logging
import math
import os
import pickle as _pickle
import time as time_mod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result container (same shape as NeuralGCMResult)
# ---------------------------------------------------------------------------

@dataclass
class GraphCastResult:
    """Metadata from a GraphCast inference run."""
    model_name: str = "GraphCast_operational_0.25deg"
    init_time: str = ""
    forecast_hours: int = 168
    inference_time_s: float = 0.0
    data_fetch_time_s: float = 0.0
    stations_extracted: int = 0
    grid_shape: str = ""


# ---------------------------------------------------------------------------
# GCS paths
# ---------------------------------------------------------------------------

ERA5_PATH = "gs://gcp-public-data-arco-era5/ar/full_37-1h-0p25deg-chunk-1.zarr-v3"
GCS_BUCKET = "dm_graphcast"
GCS_PREFIX = "graphcast/"
MODEL_NAME = (
    "GraphCast_operational - ERA5-HRES 1979-2021 - resolution 0.25 "
    "- pressure levels 13 - mesh 2to6 - precipitation output only.npz"
)
FORECAST_STEPS = 28  # 7 days × 4 steps/day at 6h intervals


# ---------------------------------------------------------------------------
# Unit conversion helpers (shared with neuralgcm_client.py)
# ---------------------------------------------------------------------------

def _specific_humidity_to_rh(q_kg_kg: float, temp_c: float, pressure_hpa: float) -> float:
    """Convert specific humidity (kg/kg) to relative humidity (%)."""
    if temp_c < -40 or q_kg_kg <= 0:
        return 0.0
    es = 6.112 * math.exp(17.67 * temp_c / (temp_c + 243.5))
    w = q_kg_kg / (1.0 - q_kg_kg)
    ws = 0.622 * es / (pressure_hpa - es) if pressure_hpa > es else 1.0
    rh = (w / ws) * 100.0 if ws > 0 else 0.0
    return max(0.0, min(100.0, rh))


def _uv_to_speed_dir(u: float, v: float) -> Tuple[float, float]:
    """Convert u,v wind components (m/s) to speed (km/h) and direction (degrees)."""
    speed_ms = math.sqrt(u ** 2 + v ** 2)
    speed_kmh = speed_ms * 3.6
    direction = (270.0 - math.degrees(math.atan2(v, u))) % 360.0
    return round(speed_kmh, 1), round(direction, 1)


def _surface_pressure_from_altitude(altitude_m: float) -> float:
    """Estimate surface pressure (hPa) from station altitude."""
    if altitude_m <= 0:
        return 1013.25
    return 1013.25 * (1.0 - 0.0065 * altitude_m / 288.15) ** 5.2561


def _best_pressure_level(altitude_m: float) -> int:
    """Select pressure level closest to station's surface pressure."""
    surface_p = _surface_pressure_from_altitude(altitude_m)
    candidates = [1000, 925, 850, 700, 600, 500, 400, 300, 250, 200, 150, 100, 50]
    best = 1000
    for level in candidates:
        if level <= surface_p + 10:
            best = level
            break
    return best


# ---------------------------------------------------------------------------
# ERA5 disk cache (survives across forecasts for the same date)
# ---------------------------------------------------------------------------

_ERA5_CACHE_DIR = os.environ.get("GRAPHCAST_ERA5_CACHE", "/tmp/graphcast_era5_cache")
os.makedirs(_ERA5_CACHE_DIR, exist_ok=True)


def _era5_cache_path(target_date: str) -> str:
    return os.path.join(_ERA5_CACHE_DIR, f"era5_prepared_{target_date}.pkl")


def _load_cached_era5(target_date: str):
    path = _era5_cache_path(target_date)
    if os.path.exists(path):
        with open(path, "rb") as f:
            return _pickle.load(f)
    return None


def _save_era5_cache(target_date: str, inputs, targets, forcings):
    path = _era5_cache_path(target_date)
    with open(path, "wb") as f:
        _pickle.dump((inputs, targets, forcings), f)


# ---------------------------------------------------------------------------
# GraphCast Client
# ---------------------------------------------------------------------------

class GraphCastClient:
    """Runs GraphCast inference on GPU and extracts station-level forecasts.

    Usage:
        client = GraphCastClient()
        forecasts, meta = await client.get_forecasts_batch(stations)
        # forecasts: Dict[station_id, List[Dict]] -- same format as NeuralGCMClient
        # meta: GraphCastResult with inference stats
    """

    def __init__(self, forecast_hours: int = 168):
        self.model_name = "GraphCast_operational_0.25deg"
        self.forecast_hours = forecast_hours
        self._params = None
        self._state = None
        self._model_config = None
        self._task_config = None
        self._diffs_stddev = None
        self._mean_by_level = None
        self._stddev_by_level = None
        self._run_forward_jitted = None

    # ------------------------------------------------------------------
    # Lazy loading
    # ------------------------------------------------------------------

    def _ensure_model(self):
        """Load GraphCast checkpoint and normalization stats from GCS."""
        if self._params is not None:
            return

        os.environ.setdefault("XLA_PYTHON_CLIENT_PREALLOCATE", "false")
        os.environ.setdefault("XLA_PYTHON_CLIENT_MEM_FRACTION", "0.95")

        import dataclasses as _dc
        import functools
        import haiku as hk
        import jax
        from google.cloud import storage
        from graphcast import (
            autoregressive,
            casting,
            checkpoint,
            graphcast,
            normalization,
        )

        log.info("Loading GraphCast_operational from GCS...")
        t0 = time_mod.time()

        gcs_client = storage.Client.create_anonymous_client()
        gcs_bucket = gcs_client.get_bucket(GCS_BUCKET)

        # Load checkpoint
        ckpt_blob = f"{GCS_PREFIX}params/{MODEL_NAME}"
        log.info("Downloading checkpoint: %s", ckpt_blob)
        with gcs_bucket.blob(ckpt_blob).open("rb") as f:
            ckpt = checkpoint.load(f, graphcast.CheckPoint)
        self._params = ckpt.params
        self._state = {}
        self._model_config = ckpt.model_config
        self._task_config = ckpt.task_config
        log.info("Checkpoint loaded: %s", self._model_config)

        # Load normalization statistics
        with gcs_bucket.blob(f"{GCS_PREFIX}stats/diffs_stddev_by_level.nc").open("rb") as f:
            import xarray
            self._diffs_stddev = xarray.load_dataset(f).compute()
        with gcs_bucket.blob(f"{GCS_PREFIX}stats/mean_by_level.nc").open("rb") as f:
            self._mean_by_level = xarray.load_dataset(f).compute()
        with gcs_bucket.blob(f"{GCS_PREFIX}stats/stddev_by_level.nc").open("rb") as f:
            self._stddev_by_level = xarray.load_dataset(f).compute()
        log.info("Normalization stats loaded")

        # Build jitted forward function
        diffs_stddev = self._diffs_stddev
        mean_by_level = self._mean_by_level
        stddev_by_level = self._stddev_by_level

        def construct_wrapped_graphcast(model_config, task_config):
            predictor = graphcast.GraphCast(model_config, task_config)
            predictor = casting.Bfloat16Cast(predictor)
            predictor = normalization.InputsAndResiduals(
                predictor,
                diffs_stddev_by_level=diffs_stddev,
                mean_by_level=mean_by_level,
                stddev_by_level=stddev_by_level,
            )
            predictor = autoregressive.Predictor(
                predictor, gradient_checkpointing=True)
            return predictor

        @hk.transform_with_state
        def run_forward(model_config, task_config, inputs, targets_template, forcings):
            predictor = construct_wrapped_graphcast(model_config, task_config)
            return predictor(
                inputs, targets_template=targets_template, forcings=forcings)

        def with_configs(fn):
            return functools.partial(
                fn, model_config=self._model_config, task_config=self._task_config)

        def with_params(fn):
            return functools.partial(fn, params=self._params, state=self._state)

        def drop_state(fn):
            return lambda **kw: fn(**kw)[0]

        self._run_forward_jitted = drop_state(with_params(jax.jit(with_configs(
            run_forward.apply))))

        log.info("GraphCast loaded in %.1fs", time_mod.time() - t0)

    # ------------------------------------------------------------------
    # ERA5 data preparation
    # ------------------------------------------------------------------

    def _fetch_era5_sync(self, target_date: str) -> Tuple[Any, Any, Any]:
        """Fetch ERA5 and prepare inputs/targets/forcings for GraphCast.

        GraphCast needs 2 consecutive timesteps (t-6h, t) as input.
        Returns (inputs, targets_template, forcings) ready for inference.
        Uses disk cache to avoid redundant downloads.
        """
        import dataclasses as _dc
        import numpy as np
        import xarray

        from graphcast import data_utils

        # Check cache first
        cached = _load_cached_era5(target_date)
        if cached is not None:
            log.info("ERA5 cache hit for %s", target_date)
            return cached

        log.info("Opening ARCO ERA5 Zarr for %s...", target_date)
        gcs_opts = {"token": "anon"}
        full_ds = xarray.open_zarr(ERA5_PATH, chunks=None,
                                   storage_options=gcs_opts, consolidated=True)

        # Target time: noon UTC on the requested date
        target = np.datetime64(f"{target_date}T12:00")
        t0 = full_ds.time.sel(time=target - np.timedelta64(6, "h"), method="nearest").values
        t1 = full_ds.time.sel(time=target, method="nearest").values
        log.info("ERA5 timesteps: %s, %s", t0, t1)

        # Identify variable categories from task_config
        target_vars = set(self._task_config.target_variables)
        forcing_vars = set(self._task_config.forcing_variables)
        input_vars = set(self._task_config.input_variables)
        static_vars = input_vars - target_vars - forcing_vars
        dynamic_vars = input_vars - static_vars

        all_needed = input_vars | target_vars | forcing_vars | {"total_precipitation_6hr"}
        available = [v for v in all_needed if v in full_ds]
        missing = all_needed - set(available)
        if missing:
            log.warning("ERA5 missing variables: %s (will be derived or zero-filled)", missing)

        # Pressure levels matching the model
        pressure_levels = list(self._task_config.pressure_levels)

        # Build the target time range for the forecast
        forecast_times = [t1 + np.timedelta64(i * 6, "h") for i in range(1, FORECAST_STEPS + 1)]
        input_times = [t0, t1]
        all_times = input_times + forecast_times

        # Split dynamic vars: heavy (pressure-level) vs surface-only forcing
        dynamic_available = [v for v in available if v not in static_vars]
        forcing_available = [v for v in dynamic_available if v in forcing_vars]
        heavy_available = [v for v in dynamic_available if v not in forcing_vars]

        # Pre-select pressure levels to avoid loading all 37 then filtering
        level_sel = {}
        if "level" in full_ds.dims and pressure_levels:
            era5_levels = full_ds.level.values
            sel_levels = [lvl for lvl in pressure_levels if lvl in era5_levels]
            if sel_levels:
                level_sel = {"level": sel_levels}

        # Stage 1: Input timesteps (2) with ALL dynamic vars at selected levels
        log.info("Fetching %d vars at %d input timesteps (+ level filter)...",
                 len(dynamic_available), len(input_times))
        ds_input = full_ds[dynamic_available].sel(time=input_times, **level_sel).compute()

        # Stage 2: Forecast timesteps (28) with only forcing vars (surface, no levels)
        # Heavy vars get NaN'd in targets anyway
        log.info("Fetching %d forcing vars at %d forecast timesteps...",
                 len(forcing_available), len(forecast_times))
        ds_forecast_forcing = full_ds[forcing_available].sel(time=forecast_times).compute()

        # Zero-fill heavy vars at forecast timesteps (targets_template * NaN)
        for var in heavy_available:
            template = ds_input[var].isel(time=0)
            shape = (len(forecast_times),) + template.shape
            ds_forecast_forcing[var] = xarray.DataArray(
                np.zeros(shape, dtype=np.float32),
                dims=["time"] + list(template.dims),
                coords={d: template.coords[d] for d in template.dims},
            ).assign_coords(time=forecast_times)

        if level_sel and "level" in ds_forecast_forcing.dims:
            ds_forecast_forcing = ds_forecast_forcing.sel(**level_sel)

        # Combine input + forecast
        ds = xarray.concat([ds_input, ds_forecast_forcing], dim="time")

        # Load static variables (no time dimension)
        for svar in static_vars:
            if svar in full_ds:
                static_data = full_ds[svar].sel(time=t1).compute()
                if "time" in static_data.dims:
                    static_data = static_data.drop_vars("time")
                ds[svar] = static_data
                log.info("Loaded static var %s", svar)
            else:
                lat_dim = "latitude" if "latitude" in ds.dims else "lat"
                lon_dim = "longitude" if "longitude" in ds.dims else "lon"
                shape = (ds.sizes[lat_dim], ds.sizes[lon_dim])
                ds[svar] = xarray.DataArray(
                    np.zeros(shape, dtype=np.float32),
                    dims=[lat_dim, lon_dim],
                )
                log.info("Created zero placeholder for missing static var %s", svar)

        # Fill NaN
        for var in ds.data_vars:
            if ds[var].isnull().any():
                mean_val = float(ds[var].mean(skipna=True).values)
                if np.isnan(mean_val):
                    ds[var] = ds[var].fillna(0.0)
                else:
                    ds[var] = ds[var].fillna(mean_val)

        # Rename dims to match GraphCast expectations
        rename_map = {}
        if "latitude" in ds.dims:
            rename_map["latitude"] = "lat"
        if "longitude" in ds.dims:
            rename_map["longitude"] = "lon"
        if rename_map:
            ds = ds.rename(rename_map)

        # Restructure time: calendar timestamps → lead-time deltas
        actual_times = ds.time.values
        t_init = actual_times[0]
        lead_times = actual_times - t_init
        ds = ds.assign_coords(time=lead_times)

        # Add batch dimension
        if "batch" not in ds.dims:
            ds = ds.expand_dims("batch", axis=0)

        # Assign datetime as a (batch, time) coordinate
        datetime_2d = np.expand_dims(actual_times, axis=0)
        ds = ds.assign_coords(datetime=(["batch", "time"], datetime_2d))

        # Add total_precipitation_6hr placeholder if missing
        if "total_precipitation_6hr" not in ds:
            tp_shape = (ds.sizes["batch"], ds.sizes["time"],
                        ds.sizes["lat"], ds.sizes["lon"])
            ds["total_precipitation_6hr"] = xarray.DataArray(
                np.zeros(tp_shape, dtype=np.float32),
                dims=["batch", "time", "lat", "lon"],
            )

        # Extract inputs, targets_template, forcings
        target_lead_times = slice("6h", f"{FORECAST_STEPS * 6}h")
        inputs, targets, forcings = data_utils.extract_inputs_targets_forcings(
            ds,
            target_lead_times=target_lead_times,
            **_dc.asdict(self._task_config),
        )

        # Cache for next time
        _save_era5_cache(target_date, inputs, targets, forcings)
        log.info("ERA5 cached to disk for %s", target_date)

        return inputs, targets, forcings

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def _run_inference_sync(self, target_date: str) -> Tuple[Any, float, float]:
        """Run GraphCast forecast for a target date (synchronous, GPU).

        Returns (predictions_dataset, inference_time_s, fetch_time_s).
        """
        import jax
        import numpy as np

        t0 = time_mod.time()
        inputs, targets_template, forcings = self._fetch_era5_sync(target_date)
        fetch_s = time_mod.time() - t0

        log.info("Running GraphCast inference (%d steps)...", FORECAST_STEPS)
        t1 = time_mod.time()
        predictions = self._run_forward_jitted(
            rng=jax.random.PRNGKey(0),
            inputs=inputs,
            targets_template=targets_template * np.nan,
            forcings=forcings,
        )
        inference_s = time_mod.time() - t1
        log.info("GraphCast inference completed in %.1fs", inference_s)

        return predictions, inference_s, fetch_s

    # ------------------------------------------------------------------
    # Station extraction
    # ------------------------------------------------------------------

    def _extract_station_forecasts(
        self,
        predictions,
        stations: List,
        init_time: str = "",
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Extract surface weather at each station from GraphCast's global output.

        Returns Dict[station_id, List[Dict]] — same format as NeuralGCMClient.
        """
        import numpy as np

        results: Dict[str, List[Dict[str, Any]]] = {}

        lat_name = "lat" if "lat" in predictions.dims else "latitude"
        lon_name = "lon" if "lon" in predictions.dims else "longitude"
        level_name = "level" if "level" in predictions.dims else "pressure_level"

        has_temp = "temperature" in predictions
        has_q = "specific_humidity" in predictions
        has_u = "u_component_of_wind" in predictions
        has_v = "v_component_of_wind" in predictions
        has_2m_temp = "2m_temperature" in predictions
        precip_var = next(
            (v for v in ("total_precipitation_6hr", "total_precipitation",
                         "precipitation", "precipitation_rate")
             if v in predictions), None)

        lon_values = predictions[lon_name].values
        uses_360 = float(lon_values.max()) > 180

        # Remove batch dim if present
        if "batch" in predictions.dims:
            predictions = predictions.isel(batch=0)

        # Get actual datetimes — predictions may only have lead-time deltas,
        # not calendar timestamps. Reconstruct from init_time + deltas.
        actual_times = None
        if "datetime" in predictions.coords:
            actual_times = predictions.datetime.values
            if actual_times.ndim > 1:
                actual_times = actual_times[0]
        if actual_times is None and init_time:
            # Reconstruct absolute timestamps from init_time + lead-time deltas
            t_init = np.datetime64(f"{init_time}T06:00")  # t0 = 06:00 UTC
            time_deltas = predictions.time.values
            actual_times = np.array([t_init + td for td in time_deltas])

        for station in stations:
            try:
                stn_lon = station.lon
                if uses_360 and stn_lon < 0:
                    stn_lon += 360.0
                elif not uses_360 and stn_lon > 180:
                    stn_lon -= 360.0

                point = predictions.sel(
                    **{lat_name: station.lat, lon_name: stn_lon},
                    method="nearest",
                )

                target_level = _best_pressure_level(station.altitude_m)
                surface_p = _surface_pressure_from_altitude(station.altitude_m)

                forecasts = []
                n_times = len(point.time)

                for t_idx in range(n_times):
                    step = point.isel(time=t_idx)

                    # Format timestamp
                    if actual_times is not None:
                        ts_str = str(np.datetime_as_string(
                            actual_times[t_idx], unit="s")).replace("T", " ")
                    else:
                        ts_str = str(step.time.values)

                    # Temperature (K → °C) — prefer 2m_temperature
                    temp_c = None
                    if has_2m_temp:
                        try:
                            temp_c = round(float(step["2m_temperature"]) - 273.15, 1)
                        except Exception:
                            pass
                    if temp_c is None and has_temp:
                        try:
                            temp_k = float(step["temperature"].sel(
                                **{level_name: target_level}, method="nearest"))
                            temp_c = round(temp_k - 273.15, 1)
                        except Exception:
                            pass

                    # Humidity
                    rh = None
                    if has_q and temp_c is not None:
                        try:
                            q = float(step["specific_humidity"].sel(
                                **{level_name: target_level}, method="nearest"))
                            rh = round(_specific_humidity_to_rh(
                                q, temp_c, float(target_level)), 1)
                        except Exception:
                            pass

                    # Wind — prefer 10m components
                    wind_speed, wind_dir = None, None
                    if "10m_u_component_of_wind" in step and "10m_v_component_of_wind" in step:
                        try:
                            u = float(step["10m_u_component_of_wind"])
                            v = float(step["10m_v_component_of_wind"])
                            wind_speed, wind_dir = _uv_to_speed_dir(u, v)
                        except Exception:
                            pass
                    if wind_speed is None and has_u and has_v:
                        try:
                            u = float(step["u_component_of_wind"].sel(
                                **{level_name: target_level}, method="nearest"))
                            v = float(step["v_component_of_wind"].sel(
                                **{level_name: target_level}, method="nearest"))
                            wind_speed, wind_dir = _uv_to_speed_dir(u, v)
                        except Exception:
                            pass

                    # Precipitation
                    rainfall = 0.0
                    if precip_var:
                        try:
                            pval = float(step[precip_var])
                            # GraphCast outputs total_precipitation_6hr in meters
                            if abs(pval) < 1.0:
                                pval *= 1000.0
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
                        "source": "graphcast",
                    })

                results[station.station_id] = forecasts

            except Exception as exc:
                log.warning(
                    "Failed to extract GraphCast forecast for %s: %s",
                    station.station_id, exc,
                )
                continue

        return results

    # ------------------------------------------------------------------
    # Regional grid extraction (for downscaling)
    # ------------------------------------------------------------------

    def _extract_regional_grid(
        self,
        predictions,
        lat_range: Tuple[float, float] = (7.5, 14.5),
        lon_range: Tuple[float, float] = (74.5, 81.5),
    ) -> List[Dict[str, Any]]:
        """Extract a regional subgrid from GraphCast predictions for downscaling.

        Returns a flat list of {lat, lon, temperature, humidity, rainfall, ...}
        dicts — one per grid point, using day-0 forecast values. Compatible with
        IDWDownscaler's grid format (same shape as NASA POWER grid).
        """
        import numpy as np

        lat_name = "lat" if "lat" in predictions.dims else "latitude"
        lon_name = "lon" if "lon" in predictions.dims else "longitude"
        level_name = "level" if "level" in predictions.dims else "pressure_level"

        # Remove batch dim
        preds = predictions.isel(batch=0) if "batch" in predictions.dims else predictions
        # Use first forecast timestep (day 0, 6h out)
        step = preds.isel(time=0)

        has_2m_temp = "2m_temperature" in step
        has_temp = "temperature" in step
        precip_var = next(
            (v for v in ("total_precipitation_6hr", "total_precipitation")
             if v in step), None)

        # Select regional box
        lats = step[lat_name].values
        lons = step[lon_name].values
        lat_mask = (lats >= lat_range[0]) & (lats <= lat_range[1])
        lon_mask = (lons >= lon_range[0]) & (lons <= lon_range[1])

        grid = []
        for lat_idx in np.where(lat_mask)[0]:
            for lon_idx in np.where(lon_mask)[0]:
                lat_val = float(lats[lat_idx])
                lon_val = float(lons[lon_idx])

                point = step.isel(**{lat_name: lat_idx, lon_name: lon_idx})

                # Temperature
                temp_c = None
                if has_2m_temp:
                    try:
                        temp_c = round(float(point["2m_temperature"]) - 273.15, 1)
                    except Exception:
                        pass
                if temp_c is None and has_temp:
                    try:
                        temp_k = float(point["temperature"].sel(
                            **{level_name: 1000}, method="nearest"))
                        temp_c = round(temp_k - 273.15, 1)
                    except Exception:
                        pass

                # Humidity
                rh = None
                if "specific_humidity" in point and temp_c is not None:
                    try:
                        q = float(point["specific_humidity"].sel(
                            **{level_name: 1000}, method="nearest"))
                        rh = round(_specific_humidity_to_rh(q, temp_c, 1000.0), 1)
                    except Exception:
                        pass

                # Rainfall
                rainfall = 0.0
                if precip_var:
                    try:
                        pval = float(point[precip_var])
                        if abs(pval) < 1.0:
                            pval *= 1000.0
                        rainfall = round(max(0.0, pval), 1)
                    except Exception:
                        pass

                grid.append({
                    "lat": lat_val,
                    "lon": lon_val,
                    "temperature": temp_c,
                    "humidity": rh,
                    "rainfall": rainfall,
                })

        log.info("Regional grid extracted: %d points (%.1f-%.1f°N, %.1f-%.1f°E)",
                 len(grid), lat_range[0], lat_range[1], lon_range[0], lon_range[1])
        return grid

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_forecasts_batch(
        self,
        stations: List,
        target_date: str | None = None,
    ) -> Tuple[Dict[str, List[Dict[str, Any]]], GraphCastResult]:
        """Run GraphCast and return forecasts for all stations.

        One inference pass covers all 20 stations (global model).
        If target_date is provided (ISO format), uses ERA5 initial
        conditions from that historical date.

        Returns:
            forecasts: Dict[station_id, List[Dict]] — same format as NeuralGCMClient
            meta: GraphCastResult with inference stats
        """
        import asyncio
        import numpy as np

        meta = GraphCastResult()

        # Load model (first call downloads checkpoint from GCS, ~30s)
        self._ensure_model()

        # Determine the forecast date
        if target_date is None:
            now = np.datetime64("now")
            for lag_days in range(5, 12):
                candidate = now - np.timedelta64(lag_days * 24, "h")
                target_date = str(np.datetime_as_string(candidate, unit="D"))
                break

        meta.init_time = target_date

        loop = asyncio.get_event_loop()

        # Run inference on GPU (blocking, in executor)
        predictions, inference_s, fetch_s = await loop.run_in_executor(
            None, self._run_inference_sync, target_date
        )
        meta.inference_time_s = round(inference_s, 1)
        meta.data_fetch_time_s = round(fetch_s, 1)

        # Log grid shape
        try:
            shape_parts = [f"{d}={predictions.dims[d]}" for d in predictions.dims]
            meta.grid_shape = " × ".join(shape_parts)
        except Exception:
            pass

        # Extract station-level forecasts from global grid
        forecasts = self._extract_station_forecasts(predictions, stations, init_time=target_date)
        meta.stations_extracted = len(forecasts)

        # Extract regional subgrid for downscaling (Kerala/TN bounding box)
        # This replaces NASA POWER for temperature interpolation to farmer GPS
        self.regional_grid = self._extract_regional_grid(predictions)

        log.info(
            "GraphCast complete: %d stations, init=%s, inference=%.1fs, fetch=%.1fs",
            meta.stations_extracted, meta.init_time,
            meta.inference_time_s, meta.data_fetch_time_s,
        )

        return forecasts, meta


# ---------------------------------------------------------------------------
# Module-level availability check
# ---------------------------------------------------------------------------

def is_graphcast_available() -> bool:
    """Check if GraphCast and its dependencies (JAX, etc.) are installed."""
    missing = []
    for pkg in ("graphcast", "jax", "haiku", "xarray"):
        try:
            __import__(pkg)
        except ImportError:
            # haiku is imported as 'haiku' but the package name is 'dm-haiku'
            if pkg == "haiku":
                try:
                    import haiku  # noqa: F401
                except ImportError:
                    missing.append("dm-haiku")
            else:
                missing.append(pkg)
    if missing:
        log.warning("GraphCast unavailable — missing packages: %s", ", ".join(missing))
        return False

    # Check for sufficient GPU memory (GraphCast 0.25° needs ~60GB)
    try:
        import jax
        devices = jax.devices()
        if not devices:
            log.warning("GraphCast unavailable — no JAX devices")
            return False
        platform = str(devices[0].platform)
        if platform == "cpu":
            log.warning("GraphCast unavailable — no GPU (CPU only)")
            return False
    except Exception:
        pass

    return True


def get_graphcast_device() -> str:
    """Return the JAX device type (cpu/gpu/tpu) if available."""
    try:
        import jax
        devices = jax.devices()
        if devices:
            return str(devices[0].platform)
        return "unknown"
    except ImportError:
        return "not_installed"
