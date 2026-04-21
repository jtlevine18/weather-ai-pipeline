"""
GenCast forecaster — Google DeepMind's 1.0° probabilistic ensemble weather model.

Runs GenCast 1.0° on GPU (JAX) and extracts per-station rainfall ensembles for
all configured stations in a single inference pass per ensemble batch. Produces
a 20-member ensemble (5 batches of 4 members, pmap'd across 4 local devices)
from which we derive rainfall quantiles (p10/p50/p90) and threshold exceedance
probabilities (P(rain>1mm), P(rain>5mm), P(rain>15mm)) at the 24–48h horizon.

Hybrid companion to GraphCast: GraphCast produces deterministic point forecasts
(temperature, wind, humidity, scalar rainfall) while GenCast contributes the
probabilistic rainfall signal used for farmer-threshold advisories.

Initial conditions: ERA5 reanalysis from Google's ARCO ERA5 Zarr archive
(same source as GraphCast — free, no auth, ~5-day lag via ERA5T), coarsened
from 0.25° to 1.0° to match the model's native grid before inference.

Requires 4× A100 80GB GPU (host RAM ~568 GB for JIT compile). Degrades
gracefully: if GenCast is unavailable, the pipeline continues with GraphCast
deterministic rainfall only and `rain_prob_*` stays NULL.

All heavy imports (graphcast, jax, xarray, haiku) are lazy so the rest of the
pipeline works on CPU-only machines without these packages installed.

The seven compat shims from the Phase 0 reference load test
(`scripts/gencast_load_test.py`) are preserved verbatim — every one is
load-bearing for the JAX 0.4.27 + xarray ≥2024.10 + graphcast combo.
"""

from __future__ import annotations

import logging
import os
import time as time_mod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

# Compat shim #1 (module-level — must fire before any JAX import).
# On-demand XLA allocation instead of 90% upfront reservation. Must happen at
# module level because is_gencast_available() triggers JAX init before the
# client ever instantiates.
os.environ.setdefault("XLA_PYTHON_CLIENT_PREALLOCATE", "false")
os.environ.setdefault("XLA_PYTHON_CLIENT_MEM_FRACTION", "0.95")

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class GenCastResult:
    """Metadata from a GenCast inference run.

    Attributes are a sealed contract — Phase 2 (pipeline + database writes)
    depends on exactly this shape.
    """
    model_used: str = ""              # "gencast_1p0_full" | "gencast_1p0_mini"
    checkpoint_name: str = ""         # exact .npz filename used
    ensemble_size: int = 0            # actual N members returned (may be < requested if batches failed)
    rollout_wall_s: float = 0.0       # wall-clock seconds for the full forecast
    target_date: str = ""             # ISO date string of the forecast init
    horizon_hours: int = 168
    step_hours: int = 12
    members_per_batch: int = 4        # usually 4 (= num local devices)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ERA5_PATH = "gs://gcp-public-data-arco-era5/ar/full_37-1h-0p25deg-chunk-1.zarr-v3"
GCS_BUCKET = "dm_graphcast"
GENCAST_PARAMS_PREFIX = "gencast/params/"
GENCAST_STATS_PREFIX = "gencast/stats/"

NATIVE_STEP_H = 12                      # GenCast native 12h step
FORECAST_HORIZON_H = 168                # 7-day horizon
N_STEPS = FORECAST_HORIZON_H // NATIVE_STEP_H  # 14 forecast steps

# 24-48h window aggregation: a single ensemble "rainfall" value is the sum of
# the rainfall increments at lead 24h (index 1, the second 12h step) and 36h
# (index 2, the third 12h step). We use summed 24-48h — the full "tomorrow"
# window from a midnight init — rather than just the 36h step so farmer
# advisories reflect day-scale totals. Phase 2 writes this one scalar per
# station per day alongside the quantiles + probabilities.
WINDOW_START_IDX = 1  # lead time 24h (step index 1 since step 0 is 12h)
WINDOW_END_IDX = 2    # lead time 36h (inclusive)

CHECKPOINT_PRIMARY_MATCH = "1p0deg <2019"   # Full
CHECKPOINT_FALLBACK_MATCH = "1p0deg Mini"   # Mini
MODEL_TAG_FULL = "gencast_1p0_full"
MODEL_TAG_MINI = "gencast_1p0_mini"


# ---------------------------------------------------------------------------
# Compat shims installed on-demand (shims #2–#4, applied before graphcast.rollout
# import — lifted verbatim from scripts/gencast_load_test.py)
# ---------------------------------------------------------------------------

def _install_rollout_compat_shims() -> None:
    """Install the compat shims graphcast/rollout.py relies on.

    Three shims, all load-bearing:
    #2: jax.P alias → jax.sharding.PartitionSpec (added top-level in JAX 0.4.30+;
        we pin 0.4.27 so backfill).
    #3: jax.NamedSharding alias → jax.sharding.NamedSharding (same reason).
    #4: xarray.Dataset.__init__ monkey-patch so `Dataset(dataset)` silently
        copies instead of raising (xarray ≤2024.9 silently copied; ≥2024.10
        raises TypeError, and graphcast/rollout.py still uses the old idiom).

    Must run before `from graphcast import rollout`.
    """
    import jax
    import xarray

    if not hasattr(jax, "P"):
        jax.P = jax.sharding.PartitionSpec
    if not hasattr(jax, "NamedSharding"):
        jax.NamedSharding = jax.sharding.NamedSharding

    # Only install the xarray patch once — repeated installs would wrap the
    # already-wrapped init and recurse.
    if getattr(xarray.Dataset.__init__, "_gencast_compat_patched", False):
        return

    _orig_ds_init = xarray.Dataset.__init__

    def _compat_ds_init(self, data_vars=None, coords=None, attrs=None):
        if isinstance(data_vars, xarray.Dataset):
            src = data_vars
            data_vars = dict(src.data_vars)
            if coords is None:
                coords = dict(src.coords)
            if attrs is None:
                attrs = dict(src.attrs)
        _orig_ds_init(self, data_vars, coords, attrs)

    _compat_ds_init._gencast_compat_patched = True  # type: ignore[attr-defined]
    xarray.Dataset.__init__ = _compat_ds_init


# ---------------------------------------------------------------------------
# GenCast Client
# ---------------------------------------------------------------------------

class GenCastClient:
    """Runs GenCast 1.0° ensemble inference on GPU and extracts per-station
    rainfall ensembles + quantiles + threshold exceedance probabilities.

    Usage:
        client = GenCastClient(ensemble_size=20)
        per_station, meta = await client.forecast(stations)
        # per_station: Dict[station_id, dict] with rain_p10/p50/p90,
        #              rain_prob_1mm/5mm/15mm, rainfall_ensemble
        # meta: GenCastResult with model name + wall time + ensemble size

    On 4× A100, a 20-member ensemble runs as 5 batches of 4 (pmap'd one member
    per device). Each batch is driven by rollout.chunked_prediction_generator_
    multiple_runs with num_samples=4 and num_steps_per_chunk=1.
    """

    def __init__(self, ensemble_size: int = 20,
                 checkpoint_match: str = CHECKPOINT_PRIMARY_MATCH) -> None:
        self.ensemble_size = ensemble_size
        self.checkpoint_match = checkpoint_match
        # Populated lazily by _ensure_model().
        self._ckpt = None
        self._stats: Dict[str, Any] = {}
        self._bucket = None
        self._sampler_pmap = None
        self._checkpoint_name = ""
        self._model_tag = ""

    # ------------------------------------------------------------------
    # Checkpoint load with fallback (Primary "1p0deg <2019" → Mini)
    # ------------------------------------------------------------------

    def _load_checkpoint_with_fallback(self):
        """Try primary checkpoint; fall back to Mini on any failure.

        Sets self._checkpoint_name and self._model_tag as side effects.
        """
        from google.cloud import storage
        from graphcast import checkpoint, gencast

        gcs_client = storage.Client.create_anonymous_client()
        bucket = gcs_client.get_bucket(GCS_BUCKET)
        blobs = [b.name for b in bucket.list_blobs(prefix=GENCAST_PARAMS_PREFIX)]
        if not blobs:
            raise RuntimeError(
                f"no blobs under gs://{GCS_BUCKET}/{GENCAST_PARAMS_PREFIX}")

        attempts: List[Tuple[str, str]] = [
            (self.checkpoint_match, MODEL_TAG_FULL
             if CHECKPOINT_PRIMARY_MATCH.lower() in self.checkpoint_match.lower()
             else MODEL_TAG_MINI),
        ]
        if self.checkpoint_match != CHECKPOINT_FALLBACK_MATCH:
            attempts.append((CHECKPOINT_FALLBACK_MATCH, MODEL_TAG_MINI))

        last_err: Optional[Exception] = None
        for match_str, tag in attempts:
            matches = [b for b in blobs if match_str.lower() in b.lower()]
            if not matches:
                log.warning("GenCast checkpoint match %r found nothing", match_str)
                continue
            ckpt_name = matches[0]
            try:
                log.info("Loading GenCast checkpoint: %s", ckpt_name)
                with bucket.blob(ckpt_name).open("rb") as f:
                    ckpt = checkpoint.load(f, gencast.CheckPoint)
                self._checkpoint_name = ckpt_name
                self._model_tag = tag
                self._bucket = bucket
                log.info("GenCast checkpoint loaded (%s)", tag)
                return ckpt
            except Exception as exc:
                log.warning("GenCast checkpoint load failed for %s: %s",
                            ckpt_name, exc)
                last_err = exc
                continue

        raise RuntimeError(
            f"All GenCast checkpoint attempts failed. Last error: {last_err}"
        )

    def _load_stats(self) -> Dict[str, Any]:
        """Load normalization stats from GCS (optional — missing blobs are skipped)."""
        import xarray
        assert self._bucket is not None
        stats: Dict[str, Any] = {}
        for key in ("diffs_stddev_by_level", "mean_by_level",
                    "stddev_by_level", "min_by_level"):
            blob = self._bucket.blob(f"{GENCAST_STATS_PREFIX}{key}.nc")
            if not blob.exists():
                log.info("GenCast stats blob missing (optional): %s", blob.name)
                continue
            with blob.open("rb") as f:
                stats[key] = xarray.load_dataset(f).compute()
            log.debug("Loaded stats: %s", key)
        return stats

    # ------------------------------------------------------------------
    # Sampler (jitted + pmap'd forward function)
    # ------------------------------------------------------------------

    def _build_sampler(self):
        """Build jit+pmap'd forward function per DeepMind's gencast_demo_cloud_vm.ipynb.

        Ensemble parallelism is across `jax.local_devices()` via xarray_jax.pmap;
        each device holds a full copy of the model and runs one ensemble member.
        """
        import haiku as hk
        import jax
        from graphcast import gencast, nan_cleaning, normalization, xarray_jax

        ckpt = self._ckpt

        # Compat shim #7 (denoiser config): force triblockdiag_mha attention +
        # full-mask on GPU — this is what DeepMind's cloud demo uses and it is
        # the combo Phase 0 proved stable on 4× A100.
        denoiser_cfg = ckpt.denoiser_architecture_config
        if hasattr(denoiser_cfg, "sparse_transformer_config"):
            denoiser_cfg.sparse_transformer_config.attention_type = "triblockdiag_mha"
            denoiser_cfg.sparse_transformer_config.mask_type = "full"
            log.info("GenCast denoiser attention → triblockdiag_mha / full (GPU mode)")

        stats = self._stats

        def _wrap():
            p = gencast.GenCast(
                sampler_config=ckpt.sampler_config,
                task_config=ckpt.task_config,
                denoiser_architecture_config=denoiser_cfg,
                noise_config=ckpt.noise_config,
                noise_encoder_config=ckpt.noise_encoder_config,
            )
            p = normalization.InputsAndResiduals(
                p,
                diffs_stddev_by_level=stats.get("diffs_stddev_by_level"),
                mean_by_level=stats.get("mean_by_level"),
                stddev_by_level=stats.get("stddev_by_level"),
            )
            # Compat shim #5: NaNCleaner expects `fill_value` as a dict keyed
            # by variable name, NOT a scalar. Scalar form silently no-ops on
            # some graphcast commits and crashes on others.
            p = nan_cleaning.NaNCleaner(
                predictor=p,
                reintroduce_nans=True,
                fill_value={"sea_surface_temperature": 0.0},
                var_to_clean="sea_surface_temperature",
            )
            return p

        @hk.transform_with_state
        def run_forward(inputs, targets_template, forcings):
            predictor = _wrap()
            return predictor(inputs, targets_template=targets_template,
                             forcings=forcings)

        run_forward_jitted = jax.jit(
            lambda rng, i, t, f: run_forward.apply(ckpt.params, {}, rng, i, t, f)[0]
        )
        sampler_pmap = xarray_jax.pmap(run_forward_jitted, dim="sample")
        log.info("GenCast pmap'd forward ready across %d devices",
                 len(jax.local_devices()))
        return sampler_pmap

    def _ensure_model(self) -> None:
        """Lazy-load checkpoint + stats + sampler. Cached across calls."""
        if self._sampler_pmap is not None:
            return

        t0 = time_mod.time()
        log.info("Loading GenCast model (checkpoint + stats + sampler)...")
        self._ckpt = self._load_checkpoint_with_fallback()
        self._stats = self._load_stats()
        self._sampler_pmap = self._build_sampler()
        log.info("GenCast loaded in %.1fs (model=%s)",
                 time_mod.time() - t0, self._model_tag)

    # ------------------------------------------------------------------
    # ERA5 data preparation (coarsened to 1.0°)
    # ------------------------------------------------------------------

    def _prepare_era5_inputs(self, target_date):
        """Build (inputs, targets_template, forcings) for GenCast at 1.0°.

        Ported from scripts/gencast_load_test.py::_prepare_era5_inputs. The
        critical compat shims in this pass:
          • sortby("lat") / sortby("lon") before extract — samplers_utils.
            _infer_latitude_spacing needs monotonic-ascending lat.
          • Coarsen 0.25° ERA5 to 1.0° before extract — feeding 0.25° grid
            into the 1.0° model blows up the mesh2grid decoder buffer by 16×.
          • target_lead_times is the full 12h..168h slice — the rollout
            generator slices to one step at a time internally; a single-step
            slice breaks forcings wiring.
        """
        import dataclasses as _dc
        import datetime as dt
        import numpy as np
        import xarray
        from graphcast import data_utils

        log.info("Opening ARCO ERA5 Zarr for GenCast init %s...", target_date)
        full_ds = xarray.open_zarr(
            ERA5_PATH, chunks=None,
            storage_options={"token": "anon"}, consolidated=True,
        )

        def _probe_ok(date_str: str) -> bool:
            try:
                v = full_ds["2m_temperature"].sel(
                    time=np.datetime64(f"{date_str}T12:00"),
                    latitude=0, longitude=0, method="nearest",
                ).compute()
                return not bool(np.isnan(float(v.values)))
            except Exception:
                return False

        # Walk target_date back if ARCO hasn't populated it yet (same logic
        # as graphcast_client — ~5-day lag via ERA5T).
        chosen = None
        for back in range(13):
            candidate = target_date - dt.timedelta(days=back)
            if _probe_ok(candidate.isoformat()):
                chosen = candidate
                if back > 0:
                    log.warning("ERA5T unpopulated at %s; using %s (%d day(s) back)",
                                target_date, chosen, back)
                break
        if chosen is None:
            raise RuntimeError(
                f"ERA5T has no valid 2m_temperature within 12 days of "
                f"{target_date} — upstream outage"
            )
        target_date = chosen

        target = np.datetime64(f"{target_date.isoformat()}T12:00")
        t0 = full_ds.time.sel(
            time=target - np.timedelta64(NATIVE_STEP_H, "h"),
            method="nearest").values
        t1 = full_ds.time.sel(time=target, method="nearest").values
        log.info("GenCast ERA5 input pair (12h apart): t0=%s t1=%s", t0, t1)

        tc = self._ckpt.task_config
        target_vars = set(tc.target_variables)
        forcing_vars = set(tc.forcing_variables)
        input_vars = set(tc.input_variables)
        static_vars = input_vars - target_vars - forcing_vars
        dynamic_vars = input_vars - static_vars

        precip_var = f"total_precipitation_{NATIVE_STEP_H}hr"
        all_needed = input_vars | target_vars | forcing_vars | {precip_var}
        available = [v for v in all_needed if v in full_ds]
        missing = all_needed - set(available)
        if missing:
            log.warning("ERA5 missing variables: %s (derived or zero-filled)", missing)

        pressure_levels = list(tc.pressure_levels)
        forecast_times = [
            t1 + np.timedelta64(i * NATIVE_STEP_H, "h") for i in range(1, N_STEPS + 1)
        ]
        input_times = [t0, t1]

        dynamic_available = [v for v in available if v not in static_vars]
        forcing_available = [v for v in dynamic_available if v in forcing_vars]
        heavy_available = [v for v in dynamic_available if v not in forcing_vars]

        level_sel: Dict[str, Any] = {}
        if "level" in full_ds.dims and pressure_levels:
            era5_levels = full_ds.level.values
            sel_levels = [lvl for lvl in pressure_levels if lvl in era5_levels]
            if sel_levels:
                level_sel = {"level": sel_levels}

        log.info("Fetching %d dynamic vars × %d input timesteps",
                 len(dynamic_available), len(input_times))
        ds_input = full_ds[dynamic_available].sel(time=input_times, **level_sel).compute()

        critical = ("2m_temperature", "10m_u_component_of_wind",
                    "10m_v_component_of_wind", "mean_sea_level_pressure")
        for var in critical:
            if var in ds_input and bool(ds_input[var].isnull().all().item()):
                raise RuntimeError(
                    f"ERA5 input {var} is all-NaN at {target_date} — ARCO not populated"
                )

        for var in ds_input.data_vars:
            if ds_input[var].isnull().any():
                mean_val = float(ds_input[var].mean(skipna=True).values)
                ds_input[var] = ds_input[var].fillna(
                    0.0 if np.isnan(mean_val) else mean_val)

        if forcing_available:
            log.info("Fetching %d forcing vars × %d forecast timesteps",
                     len(forcing_available), len(forecast_times))
            ds_forecast_forcing = full_ds[forcing_available].sel(
                time=forecast_times).compute()
        else:
            # GenCast forcings (year/day_progress_sin/cos) are time-derived
            # and not stored in ERA5. Seed an empty time-indexed dataset; the
            # heavy-var zero-fill loop below adds the rest and
            # data_utils.extract_inputs_targets_forcings derives the time
            # forcings from the `datetime` coord assigned later.
            log.info("No real forcing vars in ERA5 — GenCast forcings are time-derived")
            ds_forecast_forcing = xarray.Dataset(
                coords={"time": np.asarray(forecast_times)}
            )

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

        ds = xarray.concat([ds_input, ds_forecast_forcing], dim="time")

        for svar in static_vars:
            if svar in full_ds:
                static_data = full_ds[svar].sel(time=t1).compute()
                if "time" in static_data.dims:
                    static_data = static_data.drop_vars("time")
                ds[svar] = static_data
            else:
                lat_dim = "latitude" if "latitude" in ds.dims else "lat"
                lon_dim = "longitude" if "longitude" in ds.dims else "lon"
                shape = (ds.sizes[lat_dim], ds.sizes[lon_dim])
                ds[svar] = xarray.DataArray(
                    np.zeros(shape, dtype=np.float32), dims=[lat_dim, lon_dim])

        for var in ds.data_vars:
            if ds[var].isnull().any():
                ds[var] = ds[var].fillna(0.0)

        rename_map: Dict[str, str] = {}
        if "latitude" in ds.dims:
            rename_map["latitude"] = "lat"
        if "longitude" in ds.dims:
            rename_map["longitude"] = "lon"
        if rename_map:
            ds = ds.rename(rename_map)

        # Compat shim #6: sortby lat/lon before extract. GenCast's
        # samplers_utils._infer_latitude_spacing requires monotonic lat; ERA5
        # is stored descending (90 → -90) and upstream concat/sel paths can
        # shuffle it. Sort ascending to be safe on both axes.
        if "lat" in ds.dims:
            ds = ds.sortby("lat")
        if "lon" in ds.dims:
            ds = ds.sortby("lon")

        # Compat shim #7 (ERA5 coarsen): downsample 0.25° ERA5 to 1.0° grid.
        # Feeding 0.25° (721 × 1440) into a 1.0° model blows up the mesh2grid
        # decoder's grid-side buffer by 16× — observed 17.8 GB for
        # f32[1,3114720,1536] where 3114720 = 3 × 721 × 1440. Must happen
        # before extract.
        new_lat = np.arange(-90.0, 90.0 + 0.5, 1.0)  # 181 points
        new_lon = np.arange(0.0, 360.0, 1.0)         # 360 points
        log.info("Coarsening ERA5 inputs to 1.0° (%d → %d lat, %d → %d lon)",
                 ds.sizes["lat"], len(new_lat),
                 ds.sizes["lon"], len(new_lon))
        ds = ds.interp(lat=new_lat, lon=new_lon)
        log.info("Post-coarsen grid: lat=%d lon=%d", ds.sizes["lat"], ds.sizes["lon"])

        actual_times = ds.time.values
        t_init = actual_times[0]
        lead_times = actual_times - t_init
        ds = ds.assign_coords(time=lead_times)
        if "batch" not in ds.dims:
            ds = ds.expand_dims("batch", axis=0)
        datetime_2d = np.expand_dims(actual_times, axis=0)
        ds = ds.assign_coords(datetime=(["batch", "time"], datetime_2d))

        if precip_var not in ds:
            tp_shape = (ds.sizes["batch"], ds.sizes["time"],
                        ds.sizes["lat"], ds.sizes["lon"])
            ds[precip_var] = xarray.DataArray(
                np.zeros(tp_shape, dtype=np.float32),
                dims=["batch", "time", "lat", "lon"],
            )

        # Compat shim #8: target_lead_times as full slice, NOT single step.
        # The rollout generator (chunked_prediction_generator_multiple_runs)
        # slices one step at a time internally via num_steps_per_chunk=1. A
        # single-step slice here breaks forcings wiring.
        target_lead_times = slice(f"{NATIVE_STEP_H}h",
                                  f"{N_STEPS * NATIVE_STEP_H}h")
        inputs, targets, forcings = data_utils.extract_inputs_targets_forcings(
            ds, target_lead_times=target_lead_times, **_dc.asdict(tc),
        )
        log.info("GenCast inputs: vars=%d time=%d lat=%d lon=%d",
                 len(inputs.data_vars), inputs.sizes.get("time", 0),
                 inputs.sizes.get("lat", 0), inputs.sizes.get("lon", 0))
        return inputs, targets, forcings, target_date

    # ------------------------------------------------------------------
    # Rollout — loop over ensemble batches, one batch per pmap call
    # ------------------------------------------------------------------

    def _run_ensemble_rollout(self, inputs, targets, forcings):
        """Run the ensemble as N/num_devices batches of num_devices samples.

        Returns a list of xarray.Dataset chunks (concat'd along the `sample`
        dimension across batches), plus total wall time. Each batch uses a
        deterministic PRNG key derived from `jax.random.fold_in(rng_root, i)`
        so repeated runs on the same init produce the same ensemble.

        Per the Phase 0 fix: call rollout one batch at a time with
        num_samples=num_devices, DO NOT request num_samples=ensemble_size in a
        single call — that OOMs during JIT trace.
        """
        import jax
        import numpy as np

        # Compat shims #2–#4 — must run before the rollout import.
        _install_rollout_compat_shims()
        from graphcast import rollout

        devices = jax.local_devices()
        n_devices = len(devices)
        members_per_batch = n_devices
        n_batches = max(1, self.ensemble_size // members_per_batch)
        actual_size = n_batches * members_per_batch
        if actual_size != self.ensemble_size:
            log.warning(
                "Ensemble size %d not a multiple of num_devices %d; "
                "rounding down to %d",
                self.ensemble_size, members_per_batch, actual_size,
            )

        log.info("GenCast ensemble: %d batches × %d members = %d total",
                 n_batches, members_per_batch, actual_size)

        rng_root = jax.random.PRNGKey(0)
        t_start = time_mod.time()
        per_batch_predictions: List[Any] = []

        for batch_idx in range(n_batches):
            # fold_in makes each batch deterministic yet distinct — same idea
            # as jax.random.split but addressable by index so re-runs are
            # reproducible.
            batch_key = jax.random.fold_in(rng_root, batch_idx)
            rngs = np.stack(
                [jax.random.fold_in(batch_key, j) for j in range(members_per_batch)],
                axis=0,
            )
            t_b = time_mod.time()
            log.info("  GenCast batch %d/%d (%d members) starting",
                     batch_idx + 1, n_batches, members_per_batch)
            try:
                chunks: List[Any] = []
                for step_idx, chunk in enumerate(
                    rollout.chunked_prediction_generator_multiple_runs(
                        predictor_fn=self._sampler_pmap,
                        rngs=rngs,
                        inputs=inputs,
                        targets_template=targets * np.nan,
                        forcings=forcings,
                        num_steps_per_chunk=1,
                        num_samples=members_per_batch,
                        pmap_devices=devices,
                    )
                ):
                    chunks.append(chunk)
                # Concat the per-step chunks along the time axis.
                import xarray
                batch_prediction = xarray.concat(chunks, dim="time")
                per_batch_predictions.append(batch_prediction)
                log.info("  GenCast batch %d/%d complete in %.1fs",
                         batch_idx + 1, n_batches, time_mod.time() - t_b)
            except Exception as exc:
                # Preserve whatever members succeeded; Phase 2 degrades on
                # partial ensembles by reducing `ensemble_size` in metadata.
                log.error("GenCast batch %d/%d failed: %s", batch_idx + 1,
                          n_batches, exc)
                raise

        wall = time_mod.time() - t_start
        log.info("GenCast ensemble complete: %d batches × %d members in %.1fs",
                 n_batches, members_per_batch, wall)
        return per_batch_predictions, wall, actual_size

    # ------------------------------------------------------------------
    # Station extraction — bilinear interp + aggregate to quantiles/probs
    # ------------------------------------------------------------------

    def _extract_station_ensembles(
        self,
        per_batch_predictions: List[Any],
        stations: List,
    ) -> Dict[str, Dict[str, Any]]:
        """Bilinear-interp per-member rainfall to each station (lat, lon) and
        aggregate the ensemble into quantiles + threshold probabilities.

        Each station output:
          rain_p10, rain_p50, rain_p90              — mm summed over 24–48h
          rain_prob_1mm, rain_prob_5mm, rain_prob_15mm   — fractions in [0,1]
          rainfall_ensemble                         — list[float] of length
                                                      ensemble_size (per-member
                                                      24-48h rainfall sum, mm)

        GenCast's rainfall variable is `total_precipitation_12hr` (meters per
        12h step); we convert to mm and sum the two steps that cover 24-48h.
        """
        import numpy as np
        import xarray

        results: Dict[str, Dict[str, Any]] = {}
        if not per_batch_predictions:
            return results

        # Concatenate all batches along the ensemble axis. GenCast's pmap
        # result carries a `sample` dim; concat preserves ordering so we end
        # up with shape (ensemble, time, lat, lon) for the precip variable.
        preds = xarray.concat(per_batch_predictions, dim="sample")

        lat_name = "lat" if "lat" in preds.dims else "latitude"
        lon_name = "lon" if "lon" in preds.dims else "longitude"

        if "batch" in preds.dims:
            preds = preds.isel(batch=0)

        precip_var = next(
            (v for v in ("total_precipitation_12hr", "total_precipitation_6hr",
                         "total_precipitation", "precipitation")
             if v in preds), None,
        )
        if precip_var is None:
            log.error("GenCast predictions have no recognised precipitation variable; "
                      "keys=%s", list(preds.data_vars))
            return results

        lon_values = preds[lon_name].values
        uses_360 = float(lon_values.max()) > 180.0

        # Slice the 24–48h window once. step 0 is lead 12h, so indices [1,2]
        # cover leads 24h and 36h — summed they're the 24-48h total.
        if preds.sizes.get("time", 0) <= WINDOW_END_IDX:
            log.error(
                "GenCast rollout has only %d time steps; need ≥%d for the "
                "24-48h window", preds.sizes.get("time", 0), WINDOW_END_IDX + 1,
            )
            return results
        window = preds[precip_var].isel(
            time=slice(WINDOW_START_IDX, WINDOW_END_IDX + 1)
        )

        for station in stations:
            try:
                stn_lon = float(station.lon)
                if uses_360 and stn_lon < 0:
                    stn_lon += 360.0
                elif not uses_360 and stn_lon > 180:
                    stn_lon -= 360.0

                # Bilinear interp from the 1.0° grid to the station point.
                # Using .interp (not .sel method=nearest) keeps the ensemble
                # axis unchanged — the result has shape (sample, time) post-
                # collapse of lat/lon. Phase 0 showed nearest-neighbor on 1.0°
                # put a whole farm in the wrong grid cell for several coastal
                # Kerala stations.
                point = window.interp(
                    **{lat_name: float(station.lat), lon_name: stn_lon},
                )

                # Sum across the two 12h steps (lead 24h + 36h) and convert
                # metres → mm. GenCast's total_precipitation_12hr is in metres.
                summed = point.sum(dim="time")  # shape (sample,)
                member_rainfall_m = np.asarray(summed.values, dtype=np.float32)
                member_rainfall_mm = np.clip(member_rainfall_m * 1000.0, 0.0, None)
                ensemble_list = [float(x) for x in member_rainfall_mm.tolist()]

                if len(ensemble_list) == 0:
                    continue

                arr = np.asarray(ensemble_list, dtype=np.float32)
                p10, p50, p90 = np.quantile(arr, [0.10, 0.50, 0.90])
                prob_1mm = float(np.mean(arr > 1.0))
                prob_5mm = float(np.mean(arr > 5.0))
                prob_15mm = float(np.mean(arr > 15.0))

                results[station.station_id] = {
                    "rain_p10": round(float(p10), 2),
                    "rain_p50": round(float(p50), 2),
                    "rain_p90": round(float(p90), 2),
                    "rain_prob_1mm": round(prob_1mm, 3),
                    "rain_prob_5mm": round(prob_5mm, 3),
                    "rain_prob_15mm": round(prob_15mm, 3),
                    "rainfall_ensemble": [round(x, 3) for x in ensemble_list],
                }
            except Exception as exc:
                log.warning("GenCast station extract failed for %s: %s",
                            station.station_id, exc)
                continue

        return results

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def forecast(
        self,
        stations: List,
        target_date=None,
    ) -> Tuple[Dict[str, Dict[str, Any]], GenCastResult]:
        """Run GenCast ensemble inference and return per-station probabilistic
        rainfall metrics + metadata.

        Args:
            stations: list of StationConfig — same type GraphCastClient accepts.
            target_date: optional datetime.date for forecast init. If None,
                uses today - 5 days (ERA5T lag).

        Returns:
            per_station: {station_id: {rain_p10, rain_p50, rain_p90,
                                       rain_prob_1mm, rain_prob_5mm, rain_prob_15mm,
                                       rainfall_ensemble}}
            meta: GenCastResult metadata (sealed contract for Phase 2).
        """
        import asyncio
        import datetime as dt

        meta = GenCastResult(
            horizon_hours=FORECAST_HORIZON_H,
            step_hours=NATIVE_STEP_H,
        )

        # Load model (first call downloads checkpoint + stats).
        self._ensure_model()
        meta.checkpoint_name = self._checkpoint_name
        meta.model_used = self._model_tag

        if target_date is None:
            target_date = dt.date.today() - dt.timedelta(days=5)
        meta.target_date = target_date.isoformat()

        loop = asyncio.get_event_loop()

        def _blocking():
            inputs, targets, forcings, chosen_date = self._prepare_era5_inputs(target_date)
            per_batch, wall, actual_size = self._run_ensemble_rollout(
                inputs, targets, forcings)
            return per_batch, wall, actual_size, chosen_date

        per_batch, rollout_wall, actual_size, chosen_date = await loop.run_in_executor(
            None, _blocking
        )
        meta.rollout_wall_s = round(rollout_wall, 1)
        meta.ensemble_size = actual_size
        # Use the actual date the ERA5 init resolved to (may differ from
        # requested by up to 12 days if ARCO was behind).
        meta.target_date = chosen_date.isoformat()

        # Devices count used per batch (for transparency; defaults to 4 on A100s).
        try:
            import jax
            meta.members_per_batch = len(jax.local_devices())
        except Exception:
            pass

        per_station = self._extract_station_ensembles(per_batch, stations)

        log.info(
            "GenCast complete: model=%s stations=%d ensemble=%d wall=%.1fs init=%s",
            meta.model_used, len(per_station), meta.ensemble_size,
            meta.rollout_wall_s, meta.target_date,
        )
        return per_station, meta


# ---------------------------------------------------------------------------
# Module-level availability check
# ---------------------------------------------------------------------------

def is_gencast_available() -> bool:
    """True iff: graphcast package imports, JAX sees ≥1 CUDA device, and
    GCS anonymous read works. Any failure returns False without raising —
    the pipeline falls back to GraphCast-only in that case.
    """
    # 1. graphcast + its transitive deps import.
    missing: List[str] = []
    for pkg in ("graphcast", "jax", "haiku", "xarray"):
        try:
            __import__(pkg)
        except ImportError:
            if pkg == "haiku":
                try:
                    import haiku  # noqa: F401
                except ImportError:
                    missing.append("dm-haiku")
            else:
                missing.append(pkg)
    if missing:
        log.warning("GenCast unavailable — missing packages: %s",
                    ", ".join(missing))
        return False

    # 2. JAX sees ≥1 CUDA device (GenCast 1.0° needs 4× A100 in production;
    #    we gate on "at least one CUDA device" here so the smoke test Space
    #    with a single GPU still reports True during Phase 1 bring-up).
    try:
        import jax
        devices = jax.devices()
        if not devices:
            log.warning("GenCast unavailable — no JAX devices")
            return False
        platform = str(devices[0].platform).lower()
        if platform != "gpu" and platform != "cuda":
            log.warning("GenCast unavailable — first JAX device is %s, not GPU",
                        platform)
            return False
    except Exception as exc:
        log.warning("GenCast unavailable — JAX device probe failed: %s", exc)
        return False

    # 3. GCS anonymous read to the GenCast params prefix works.
    try:
        from google.cloud import storage
        bucket = storage.Client.create_anonymous_client().get_bucket(GCS_BUCKET)
        it = bucket.list_blobs(prefix=GENCAST_PARAMS_PREFIX, max_results=1)
        if not list(it):
            log.warning("GenCast unavailable — no blobs under gs://%s/%s",
                        GCS_BUCKET, GENCAST_PARAMS_PREFIX)
            return False
    except Exception as exc:
        log.warning("GenCast unavailable — GCS probe failed: %s", exc)
        return False

    return True
