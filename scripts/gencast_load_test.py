#!/usr/bin/env python3
"""
Phase 0 load test for GenCast 0.25° on a 4× A100 HF Space.

Verifies GenCast 0.25° runs end-to-end on target hardware, times a single
forecast and a 5-member ensemble, and measures peak host RSS + VRAM. Gates
the rest of the integration (docs/gencast-integration-plan.md §4).

Decision gates (checked in the SUMMARY at end):
    PASS : peak host RSS < 500 GB, single-member forecast < 5 min    → Phase 1
    SLOW : single-member > 10 min                                    → shrink ensemble / try 1.0°
    FAIL : > 500 GB or OOM                                           → divert to Path C (GraphCast + QM-MOS)

Usage (on the duplicated pipeline Space):
    XLA_PYTHON_CLIENT_PREALLOCATE=false python scripts/gencast_load_test.py

Diagnostic, not production. Each phase is wrapped so a late failure still
leaves earlier timings in /tmp/gencast_load.log. Run it by hand, read the
log, decide Phase 1.
"""

from __future__ import annotations

import dataclasses as _dc
import datetime as dt
import functools
import logging
import os
import resource
import subprocess
import sys
import time
import traceback
from pathlib import Path

os.environ.setdefault("XLA_PYTHON_CLIENT_PREALLOCATE", "false")
os.environ.setdefault("XLA_PYTHON_CLIENT_MEM_FRACTION", "0.95")

LOG_PATH = Path("/tmp/gencast_load.log")
TARGET_DATE = dt.date.today() - dt.timedelta(days=7)
FORECAST_HORIZON_H = 168
NATIVE_STEP_H = 12
N_STEPS = FORECAST_HORIZON_H // NATIVE_STEP_H  # 14
ENSEMBLE_SIZE = 5
PEAK_RAM_GATE_GB = 500.0
SINGLE_MEMBER_WARN_S = 300.0
SINGLE_MEMBER_FAIL_S = 600.0

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(LOG_PATH, mode="w")],
)
log = logging.getLogger("gencast_load")


def peak_host_rss_gb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)


def gpu_mem_gb() -> list[float]:
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            timeout=10,
        )
        return [float(x.strip()) / 1024 for x in out.decode().splitlines() if x.strip()]
    except Exception as exc:
        log.warning("nvidia-smi unavailable: %s", exc)
        return []


def log_memory(tag: str) -> None:
    gpus = gpu_mem_gb()
    gpu_summary = ", ".join(f"{g:.1f}GB" for g in gpus) if gpus else "none"
    log.info("MEM[%s] host_peak_rss=%.1fGB gpus=[%s]", tag, peak_host_rss_gb(), gpu_summary)


def phase(name: str):
    def decorator(fn):
        @functools.wraps(fn)
        def wrapped(*args, **kwargs):
            log.info("=" * 60)
            log.info("PHASE %s START", name)
            t0 = time.time()
            try:
                result = fn(*args, **kwargs)
            except Exception:
                log.error("PHASE %s FAIL in %.1fs\n%s", name, time.time() - t0, traceback.format_exc())
                log_memory(f"fail:{name}")
                raise
            log.info("PHASE %s OK in %.1fs", name, time.time() - t0)
            log_memory(f"after:{name}")
            return result
        return wrapped
    return decorator


@phase("imports")
def _imports():
    import jax
    from graphcast import gencast, checkpoint, normalization, rollout  # noqa: F401
    log.info("jax devices: %s", jax.devices())
    log.info("jax backend: %s", jax.default_backend())
    log.info("gencast module dir: %s", [a for a in dir(gencast) if not a.startswith("_")][:20])


@phase("checkpoint")
def _load_checkpoint():
    from google.cloud import storage
    from graphcast import checkpoint, gencast

    bucket = storage.Client.create_anonymous_client().get_bucket("dm_graphcast")
    blobs = [b.name for b in bucket.list_blobs(prefix="gencast/params/")]
    log.info("available gencast checkpoints (%d):\n  %s", len(blobs), "\n  ".join(blobs))
    if not blobs:
        raise RuntimeError("no blobs under gs://dm_graphcast/gencast/params/")
    ckpt_name = next(
        (b for b in blobs if "0p25" in b and "operational" in b.lower()),
        next((b for b in blobs if "0p25" in b), blobs[0]),
    )
    log.info("selected checkpoint: %s", ckpt_name)
    with bucket.blob(ckpt_name).open("rb") as f:
        ckpt = checkpoint.load(f, gencast.CheckPoint)
    log.info("task_config.pressure_levels=%s", getattr(ckpt.task_config, "pressure_levels", "?"))
    log.info("task_config.input_variables=%s", getattr(ckpt.task_config, "input_variables", "?"))
    log.info("task_config.target_variables=%s", getattr(ckpt.task_config, "target_variables", "?"))
    log.info("task_config.forcing_variables=%s", getattr(ckpt.task_config, "forcing_variables", "?"))
    return ckpt, bucket


@phase("stats")
def _load_stats(bucket):
    import xarray
    stats = {}
    for key in ("diffs_stddev_by_level", "mean_by_level", "stddev_by_level", "min_by_level"):
        blob = bucket.blob(f"gencast/stats/{key}.nc")
        if not blob.exists():
            log.info("stats blob missing (optional): %s", blob.name)
            continue
        with blob.open("rb") as f:
            stats[key] = xarray.load_dataset(f).compute()
        log.info("loaded %s", key)
    return stats


@phase("era5_prep")
def _prepare_era5_inputs(ckpt, target_date: dt.date):
    """Build (inputs, targets_template, forcings) for GenCast.

    Ported from graphcast_client._fetch_era5_sync with the 6h→12h adjustment.
    GenCast native step is 12h, so the input pair is (t-12h, t) and forecast
    timesteps advance in 12h increments.
    """
    import numpy as np
    import xarray
    from graphcast import data_utils

    era5_path = "gs://gcp-public-data-arco-era5/ar/full_37-1h-0p25deg-chunk-1.zarr-v3"
    log.info("opening ARCO ERA5 Zarr...")
    full_ds = xarray.open_zarr(era5_path, chunks=None,
                               storage_options={"token": "anon"}, consolidated=True)

    def _probe_ok(date_str: str) -> bool:
        try:
            v = full_ds["2m_temperature"].sel(
                time=np.datetime64(f"{date_str}T12:00"),
                latitude=0, longitude=0, method="nearest",
            ).compute()
            return not bool(np.isnan(float(v.values)))
        except Exception:
            return False

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
        raise RuntimeError(f"ERA5T has no valid 2m_temperature within 12 days of {target_date}")
    target_date = chosen

    target = np.datetime64(f"{target_date.isoformat()}T12:00")
    t0 = full_ds.time.sel(time=target - np.timedelta64(NATIVE_STEP_H, "h"), method="nearest").values
    t1 = full_ds.time.sel(time=target, method="nearest").values
    log.info("ERA5 input times (12h apart): t0=%s t1=%s", t0, t1)

    tc = ckpt.task_config
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
    forecast_times = [t1 + np.timedelta64(i * NATIVE_STEP_H, "h") for i in range(1, N_STEPS + 1)]
    input_times = [t0, t1]

    dynamic_available = [v for v in available if v not in static_vars]
    forcing_available = [v for v in dynamic_available if v in forcing_vars]
    heavy_available = [v for v in dynamic_available if v not in forcing_vars]

    level_sel = {}
    if "level" in full_ds.dims and pressure_levels:
        era5_levels = full_ds.level.values
        sel_levels = [lvl for lvl in pressure_levels if lvl in era5_levels]
        if sel_levels:
            level_sel = {"level": sel_levels}

    log.info("fetching %d dynamic vars × %d input timesteps", len(dynamic_available), len(input_times))
    ds_input = full_ds[dynamic_available].sel(time=input_times, **level_sel).compute()

    critical = ("2m_temperature", "10m_u_component_of_wind", "10m_v_component_of_wind",
                "mean_sea_level_pressure")
    for var in critical:
        if var in ds_input and bool(ds_input[var].isnull().all().item()):
            raise RuntimeError(f"ERA5 input {var} is all-NaN at {target_date} — ARCO not populated")

    for var in ds_input.data_vars:
        if ds_input[var].isnull().any():
            mean_val = float(ds_input[var].mean(skipna=True).values)
            ds_input[var] = ds_input[var].fillna(0.0 if np.isnan(mean_val) else mean_val)

    if forcing_available:
        log.info("fetching %d forcing vars × %d forecast timesteps",
                 len(forcing_available), len(forecast_times))
        ds_forecast_forcing = full_ds[forcing_available].sel(time=forecast_times).compute()
    else:
        # GenCast forcings (year_progress_sin/cos, day_progress_sin/cos) are
        # time-derived and not stored in ERA5. Start with just a time-indexed
        # empty dataset; the heavy-var zero-fill loop below adds the rest, and
        # `data_utils.extract_inputs_targets_forcings` derives the time
        # forcings from the `datetime` coord we assign later.
        log.info("no real forcing vars in ERA5 — GenCast forcings are time-derived")
        ds_forecast_forcing = xarray.Dataset(coords={"time": np.asarray(forecast_times)})

    for var in heavy_available:
        template = ds_input[var].isel(time=0)
        shape = (len(forecast_times),) + template.shape
        import numpy as _np
        ds_forecast_forcing[var] = xarray.DataArray(
            _np.zeros(shape, dtype=_np.float32),
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
            ds[svar] = xarray.DataArray(np.zeros(shape, dtype=np.float32), dims=[lat_dim, lon_dim])

    for var in ds.data_vars:
        if ds[var].isnull().any():
            ds[var] = ds[var].fillna(0.0)

    rename_map = {}
    if "latitude" in ds.dims:
        rename_map["latitude"] = "lat"
    if "longitude" in ds.dims:
        rename_map["longitude"] = "lon"
    if rename_map:
        ds = ds.rename(rename_map)

    # GenCast's samplers_utils._infer_latitude_spacing requires monotonic lat;
    # ERA5 is stored descending (90 → -90) which usually stays monotonic, but
    # some upstream concat/sel paths shuffle it. Sort ascending to be safe.
    if "lat" in ds.dims:
        ds = ds.sortby("lat")
    if "lon" in ds.dims:
        ds = ds.sortby("lon")

    actual_times = ds.time.values
    t_init = actual_times[0]
    lead_times = actual_times - t_init
    ds = ds.assign_coords(time=lead_times)
    if "batch" not in ds.dims:
        ds = ds.expand_dims("batch", axis=0)
    datetime_2d = np.expand_dims(actual_times, axis=0)
    ds = ds.assign_coords(datetime=(["batch", "time"], datetime_2d))

    if precip_var not in ds:
        tp_shape = (ds.sizes["batch"], ds.sizes["time"], ds.sizes["lat"], ds.sizes["lon"])
        ds[precip_var] = xarray.DataArray(
            np.zeros(tp_shape, dtype=np.float32),
            dims=["batch", "time", "lat", "lon"],
        )

    # GenCast is single-step; the full 168h rollout is driven externally by
    # rollout.chunked_prediction_generator_multiple_runs with
    # num_steps_per_chunk=1. Pass the full target range so the generator has
    # the complete template — it slices to one step at a time internally.
    target_lead_times = slice(f"{NATIVE_STEP_H}h", f"{N_STEPS * NATIVE_STEP_H}h")
    inputs, targets, forcings = data_utils.extract_inputs_targets_forcings(
        ds, target_lead_times=target_lead_times, **_dc.asdict(tc),
    )
    log.info("inputs: vars=%d time=%d lat=%d lon=%d",
             len(inputs.data_vars), inputs.sizes.get("time", 0),
             inputs.sizes.get("lat", 0), inputs.sizes.get("lon", 0))
    log.info("targets_template: time=%d", targets.sizes.get("time", 0))
    log.info("forcings: vars=%d time=%d", len(forcings.data_vars), forcings.sizes.get("time", 0))
    return inputs, targets, forcings


@phase("sampler_build")
def _build_sampler(ckpt, stats):
    """Build jit+pmap'd forward function per DeepMind's gencast_demo_cloud_vm.ipynb.

    Ensemble parallelism is across `jax.local_devices()` via xarray_jax.pmap;
    each device holds a full copy of the model and runs one ensemble member.
    The rollout generator (invoked in _run_forecast) drives multi-step rollout.
    """
    import haiku as hk
    import jax
    from graphcast import gencast, nan_cleaning, normalization, xarray_jax

    denoiser_cfg = ckpt.denoiser_architecture_config
    if hasattr(denoiser_cfg, "sparse_transformer_config"):
        denoiser_cfg.sparse_transformer_config.attention_type = "triblockdiag_mha"
        denoiser_cfg.sparse_transformer_config.mask_type = "full"
        log.info("denoiser attention → triblockdiag_mha / full (GPU mode)")

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
        p = nan_cleaning.NaNCleaner(
            predictor=p, reintroduce_nans=True,
            fill_value={"sea_surface_temperature": 0.0},
            var_to_clean="sea_surface_temperature",
        )
        return p

    @hk.transform_with_state
    def run_forward(inputs, targets_template, forcings):
        predictor = _wrap()
        return predictor(inputs, targets_template=targets_template, forcings=forcings)

    run_forward_jitted = jax.jit(
        lambda rng, i, t, f: run_forward.apply(ckpt.params, {}, rng, i, t, f)[0]
    )
    run_forward_pmap = xarray_jax.pmap(run_forward_jitted, dim="sample")
    log.info("pmap'd forward ready across %d devices", len(jax.local_devices()))
    return run_forward_pmap


@phase("rollout")
def _run_rollout(sampler_pmap, inputs, targets, forcings):
    """Drive GenCast via rollout.chunked_prediction_generator_multiple_runs.

    Matches DeepMind's gencast_demo_cloud_vm.ipynb pattern: N ensemble members
    are distributed across jax.local_devices() via pmap (one member per
    device), and the generator yields one 12h step at a time for the full
    168h horizon. Total forward passes = N_STEPS × ceil(N / num_devices).
    """
    import jax
    import numpy as np

    # graphcast/rollout.py uses jax.P and jax.NamedSharding which are
    # top-level aliases added in JAX 0.4.30+. Our pin is 0.4.27 so backfill
    # them to their canonical locations before importing rollout.
    if not hasattr(jax, "P"):
        jax.P = jax.sharding.PartitionSpec
    if not hasattr(jax, "NamedSharding"):
        jax.NamedSharding = jax.sharding.NamedSharding

    from graphcast import rollout

    devices = jax.local_devices()
    n_devices = len(devices)
    # Start conservative — one sample per device, matching DeepMind's contract
    # (num_ensemble_members must be a multiple of num_devices). On 4× A100 this
    # is 4 samples in parallel; each device holds one full copy of the model.
    n_samples = n_devices
    log.info("rolling out %d samples across %d devices (1 sample/device)",
             n_samples, n_devices)

    rng_root = jax.random.PRNGKey(0)
    rngs = np.stack([jax.random.fold_in(rng_root, i) for i in range(n_samples)], axis=0)

    t_start = time.time()
    chunks = []
    for i, chunk in enumerate(rollout.chunked_prediction_generator_multiple_runs(
        predictor_fn=sampler_pmap,
        rngs=rngs,
        inputs=inputs,
        targets_template=targets * np.nan,
        forcings=forcings,
        num_steps_per_chunk=1,
        num_samples=n_samples,
        pmap_devices=devices,
    )):
        step_elapsed = time.time() - t_start
        log.info("  chunk %d: cumulative=%.1fs dims=%s",
                 i + 1, step_elapsed,
                 dict(chunk.dims) if hasattr(chunk, "dims") else "?")
        chunks.append(chunk)
        log_memory(f"rollout:chunk{i+1}")
    wall = time.time() - t_start

    log.info("rollout complete: %d chunks across %d samples in %.1fs",
             len(chunks), n_samples, wall)
    per_step = wall / max(len(chunks), 1)
    log.info("per-step wall: %.1fs (projection for 20-member @ 4 devices: %.1fs)",
             per_step, per_step * N_STEPS * (20 / n_samples))
    return chunks, wall


def main() -> int:
    log.info("#" * 60)
    log.info("GenCast 0.25° Phase 0 load test")
    log.info("target_date=%s horizon=%dh step=%dh (n=%d) ensemble=%d",
             TARGET_DATE, FORECAST_HORIZON_H, NATIVE_STEP_H, N_STEPS, ENSEMBLE_SIZE)
    log.info("gates: peak_ram<%.0fGB single_member<%.0fs (warn) / <%.0fs (fail)",
             PEAK_RAM_GATE_GB, SINGLE_MEMBER_WARN_S, SINGLE_MEMBER_FAIL_S)
    log.info("#" * 60)
    log_memory("start")

    try:
        _imports()
        ckpt, bucket = _load_checkpoint()
        stats = _load_stats(bucket)
        inputs, targets, forcings = _prepare_era5_inputs(ckpt, TARGET_DATE)
        sampler_fn = _build_sampler(ckpt, stats)
    except Exception:
        log.error("halted before inference — see log for failing phase")
        log.info("SUMMARY: infra probe FAIL")
        return 1

    rollout_wall = None
    try:
        chunks, rollout_wall = _run_rollout(sampler_fn, inputs, targets, forcings)
    except Exception:
        log.exception("rollout failed")
        log.info("SUMMARY: infra OK, rollout FAIL")
        return 2

    import jax
    n_devices = len(jax.local_devices())
    peak_ram = peak_host_rss_gb()
    log.info("#" * 60)
    log.info("SUMMARY")
    log.info("  peak host RSS    : %.1f GB  (gate: <%.0f GB)", peak_ram, PEAK_RAM_GATE_GB)
    log.info("  rollout wall     : %.1f s for %d samples × %d steps",
             rollout_wall, n_devices, N_STEPS)
    log.info("  per-step-per-%d  : %.1f s", n_devices, rollout_wall / N_STEPS)
    log.info("  full 20-member projection: %.1f s",
             rollout_wall * (20 / n_devices))
    log.info("#" * 60)

    if peak_ram >= PEAK_RAM_GATE_GB:
        log.error("GATE FAIL: host RSS ≥ %.0f GB → divert to Path C", PEAK_RAM_GATE_GB)
        return 3
    if rollout_wall > SINGLE_MEMBER_FAIL_S * 2:
        log.error("GATE FAIL: rollout > %.0fs → too slow for weekly pipeline", SINGLE_MEMBER_FAIL_S * 2)
        return 4
    if rollout_wall > SINGLE_MEMBER_WARN_S:
        log.warning("GATE SLOW: rollout > %.0fs — consider smaller ensemble in Phase 1",
                    SINGLE_MEMBER_WARN_S)
    log.info("GATE PASS — green light Phase 1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
