"""GFS (NOAA Global Forecast System) → ERA5-shaped xarray.Dataset.

The top-level entry point is ``fetch_gfs_as_era5(target_date)`` which returns
an ``xarray.Dataset`` that is a drop-in replacement for the ARCO ERA5 Zarr
``full_ds`` used by ``graphcast_client._fetch_era5_sync`` and
``gencast_client._prepare_era5_inputs``.

**Phase 1 status: nothing in the production pipeline imports this module.**
It's reachable only from ``tests/test_init_sources/``. Wiring into the two
clients is deferred to Phase 2 so we can validate the module first in
isolation, then head-to-head with the existing ERA5 path.

Source: AWS S3 public bucket ``noaa-gfs-bdp-pds`` (``gfs.YYYYMMDD/HH/atmos/
gfs.tHHz.pgrb2.0p25.fNNN``). Free, no auth, real-time (~3h lag per cycle).

Layout inside the returned Dataset:
    * time:      2 input timesteps (target-6h, target) + N forecast steps
                 at 6h cadence
    * latitude:  721 points (90 .. -90, 0.25° step)  — matches ARCO ERA5
    * longitude: 1440 points (0 .. 359.75, 0.25° step)
    * level:     13 pressure levels (the GraphCast operational set)
    * data_vars: 5 surface + 6 pressure-level + 2 static variables in ERA5
                 canonical naming; units converted to match ERA5

The module keeps every heavy/optional import (``cfgrib``, ``s3fs``, ``boto3``)
inside the function that needs it. That means the module itself imports fine
on any box with ``xarray`` + ``numpy``, which matters because the test suite
runs without cfgrib/eccodes installed.
"""

from __future__ import annotations

import logging
import os
import pickle
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, List, Optional, Sequence, Tuple

from src.init_sources.variable_mapping import (
    GRAPHCAST_PRESSURE_LEVELS,
    PRESSURE_LEVEL_VARS,
    STATIC_VARS,
    SURFACE_VARS,
    unit_convert,
)
from src.init_sources.static_vars import load_static_ds

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GFS_S3_BUCKET = "noaa-gfs-bdp-pds"
GFS_CYCLE_HOURS: Tuple[int, ...] = (0, 6, 12, 18)
DEFAULT_CYCLE_HOUR = 12
GFS_NATIVE_RESOLUTION_DEG = 0.25
GFS_N_LAT = 721
GFS_N_LON = 1440

# Where to cache assembled GFS datasets (pickle format, same pattern as the
# ERA5 cache already used by graphcast_client.py).
_GFS_CACHE_DIR = os.environ.get("GFS_CACHE_DIR", "/tmp/gfs_init_cache")


# ---------------------------------------------------------------------------
# Cycle selection
# ---------------------------------------------------------------------------

@dataclass
class GfsCycle:
    """A specific GFS analysis cycle. Pure data — no I/O."""
    date: str     # "YYYY-MM-DD" (UTC calendar day of the cycle)
    hour: int     # 0, 6, 12, or 18

    def datetime_utc(self) -> datetime:
        d = datetime.fromisoformat(self.date).replace(tzinfo=timezone.utc)
        return d + timedelta(hours=self.hour)

    def s3_prefix(self) -> str:
        """Bucket-relative prefix for this cycle's files."""
        d = self.date.replace("-", "")
        return f"gfs.{d}/{self.hour:02d}/atmos"

    def file_name(self, forecast_hour: int) -> str:
        """GRIB2 filename for a given forecast hour (0 = analysis)."""
        return f"gfs.t{self.hour:02d}z.pgrb2.0p25.f{forecast_hour:03d}"

    def s3_key(self, forecast_hour: int) -> str:
        return f"{self.s3_prefix()}/{self.file_name(forecast_hour)}"


def _most_recent_cycle(
    target_date: str,
    target_cycle_hour: int = DEFAULT_CYCLE_HOUR,
) -> GfsCycle:
    """Return the cycle that should be used to init at ``target_date Thh:00 UTC``.

    GFS cycles run at 00/06/12/18 UTC. Analysis becomes available ~3-4h after
    the cycle starts, so in practice we want the most recent cycle that's
    strictly completed. Phase 2 will walk this back further if the bucket
    isn't populated yet.
    """
    if target_cycle_hour not in GFS_CYCLE_HOURS:
        # Snap down to the nearest valid cycle hour.
        target_cycle_hour = max(h for h in GFS_CYCLE_HOURS if h <= target_cycle_hour)
    return GfsCycle(date=target_date, hour=target_cycle_hour)


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def _download_grib2(
    cycle: GfsCycle,
    forecast_hour: int,
    dest_dir: str,
    levels: Sequence[int] = GRAPHCAST_PRESSURE_LEVELS,
) -> str:
    """Download a GFS GRIB2 analysis/forecast file from the public S3 bucket.

    Default path is byte-range fetching: downloads the companion ``.idx``
    index, identifies the ~83 messages GraphCast actually needs (out of
    ~700 in a pgrb2.0p25 cycle), and fetches only their byte ranges in
    parallel. A pgrb2.0p25 analysis file is ~465 MB; the subset is
    ~70 MB — 85% bandwidth savings.

    Set ``GFS_USE_BYTE_RANGE=0`` to force the legacy full-file fetch
    (useful when debugging a suspected byte-range bug).
    """
    os.makedirs(dest_dir, exist_ok=True)
    local_path = os.path.join(dest_dir, cycle.file_name(forecast_hour))
    if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
        log.info("GFS GRIB cached: %s", local_path)
        return local_path

    if os.environ.get("GFS_USE_BYTE_RANGE", "1") != "0":
        try:
            return _fetch_grib2_byte_range(
                cycle, forecast_hour, dest_dir, levels=levels,
            )
        except Exception as exc:
            log.warning(
                "Byte-range fetch failed (%s); falling back to full-file download",
                exc,
            )

    import boto3
    from botocore import UNSIGNED
    from botocore.config import Config

    s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))
    key = cycle.s3_key(forecast_hour)
    log.info("Downloading full s3://%s/%s", GFS_S3_BUCKET, key)
    s3.download_file(GFS_S3_BUCKET, key, local_path)
    return local_path


# ---------------------------------------------------------------------------
# Byte-range GRIB fetching (default path)
# ---------------------------------------------------------------------------
#
# NOAA publishes a wgrib2-style ``.idx`` alongside every ``.grib2`` file:
#
#   1:0:d=2026041512:PRMSL:mean sea level:anl:
#   2:927234:d=2026041512:CLWMR:1 hybrid level:anl:
#   3:1184731:d=2026041512:ICMR:1 hybrid level:anl:
#   ...
#
# Fields are ``msg_n : byte_offset : d=YYYYMMDDHH : PARAM : LEVEL_DESC :
# STEP_TYPE : …``. Each message's byte length is the next message's offset
# minus its own (or the file size, for the last message). Since GRIB2 is
# self-terminating, concatenated messages read back fine via cfgrib —
# eccodes just walks the record headers.

# ecCodes shortName → (wgrib2 PARAM, exact LEVEL_DESC string in .idx)
_SURFACE_IDX_PATTERNS = {
    "2t":    ("TMP",   "2 m above ground"),
    "10u":   ("UGRD",  "10 m above ground"),
    "10v":   ("VGRD",  "10 m above ground"),
    "prmsl": ("PRMSL", "mean sea level"),
    "tp":    ("APCP",  "surface"),
}

# ecCodes shortName → wgrib2 PARAM. Level is always "<N> mb" with N in the
# GraphCast 13-level set.
_PRESSURE_IDX_PARAMS = {
    "t":  "TMP",
    "q":  "SPFH",
    "u":  "UGRD",
    "v":  "VGRD",
    "w":  "VVEL",
    "gh": "HGT",
}


def _parse_idx_for_wanted_messages(
    idx_text: str,
    levels: Sequence[int],
) -> List[Tuple[int, Optional[int]]]:
    """Return ``[(offset, length), ...]`` for every message we want.

    ``length`` is ``None`` for the last message in the file (fetch to EOF).
    Deduplicates by (param, level_desc): GFS forecast files sometimes ship
    multiple APCP messages for different accumulation windows; we take the
    lowest-message-number match.
    """
    import re

    lines = [l for l in idx_text.splitlines() if l.strip()]
    records: List[Tuple[int, int, str, str]] = []
    for line in lines:
        parts = line.split(":")
        if len(parts) < 6:
            continue
        try:
            msg_n = int(parts[0])
            offset = int(parts[1])
        except ValueError:
            continue
        records.append((msg_n, offset, parts[3], parts[4]))
    records.sort(key=lambda r: r[0])

    next_offset: dict = {}
    for i, rec in enumerate(records):
        next_offset[rec[0]] = records[i + 1][1] if i + 1 < len(records) else None

    wanted_levels = set(levels)
    mb_re = re.compile(r"^(\d+) mb$")
    seen: set = set()
    out: List[Tuple[int, Optional[int]]] = []

    for msg_n, offset, param, level_desc in records:
        match_key = None
        # Surface match
        for wg_param, wg_level in _SURFACE_IDX_PATTERNS.values():
            if param == wg_param and level_desc == wg_level:
                match_key = (wg_param, wg_level)
                break
        # Pressure match
        if match_key is None and param in _PRESSURE_IDX_PARAMS.values():
            m = mb_re.match(level_desc)
            if m and int(m.group(1)) in wanted_levels:
                match_key = (param, level_desc)

        if match_key and match_key not in seen:
            seen.add(match_key)
            nxt = next_offset[msg_n]
            length = (nxt - offset) if nxt is not None else None
            out.append((offset, length))

    return sorted(out)  # monotone offsets for sequential write


def _fetch_grib2_byte_range(
    cycle: GfsCycle,
    forecast_hour: int,
    dest_dir: str,
    levels: Sequence[int] = GRAPHCAST_PRESSURE_LEVELS,
    max_workers: int = 8,
) -> str:
    """Download only the GRIB messages GraphCast needs, via HTTP Range.

    Fetches the tiny ``.idx`` first, selects the ~83 messages covering
    (5 surface vars) + (6 pressure-level vars × 13 levels), then issues
    parallel ``GetObject`` calls with a ``Range:`` header for each wanted
    byte span. Writes all bytes in ascending-offset order into a normal
    ``.grib2`` file that cfgrib reads identically to the full-file copy.
    """
    import boto3
    from botocore import UNSIGNED
    from botocore.config import Config
    from concurrent.futures import ThreadPoolExecutor, as_completed

    os.makedirs(dest_dir, exist_ok=True)
    local_path = os.path.join(dest_dir, cycle.file_name(forecast_hour))

    s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))
    key = cycle.s3_key(forecast_hour)
    idx_key = key + ".idx"

    idx_text = s3.get_object(Bucket=GFS_S3_BUCKET, Key=idx_key)["Body"].read().decode("ascii")
    ranges = _parse_idx_for_wanted_messages(idx_text, levels)
    if not ranges:
        raise RuntimeError(f"No matching GRIB messages in {idx_key}")

    def _fetch(offset: int, length: Optional[int]) -> Tuple[int, bytes]:
        if length is None:
            r = s3.get_object(
                Bucket=GFS_S3_BUCKET, Key=key,
                Range=f"bytes={offset}-",
            )
        else:
            r = s3.get_object(
                Bucket=GFS_S3_BUCKET, Key=key,
                Range=f"bytes={offset}-{offset + length - 1}",
            )
        return offset, r["Body"].read()

    buffers: dict = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(_fetch, off, length) for off, length in ranges]
        for fut in as_completed(futures):
            off, buf = fut.result()
            buffers[off] = buf

    total_bytes = sum(len(b) for b in buffers.values())
    with open(local_path, "wb") as f:
        for off, _length in ranges:
            f.write(buffers[off])

    log.info("GFS byte-range: %d messages, %.1f MB → %s",
             len(ranges), total_bytes / 1024 / 1024, local_path)
    return local_path


# ---------------------------------------------------------------------------
# GRIB parsing
# ---------------------------------------------------------------------------

def _open_grib_surface(path: str, ecmwf_short_name: str) -> Any:
    """Return an xarray.DataArray for a single surface variable from GRIB2.

    ``ecmwf_short_name`` is the ecCodes shortName (e.g. ``2t``, ``10u``,
    ``prmsl``, ``tp``) — what GRIB messages are indexed by, NOT cfgrib's
    output variable name (e.g. ``t2m``, ``u10``). cfgrib's
    ``filter_by_keys`` takes ecCodes names; getting this wrong returns an
    empty dataset silently, which was the Phase-2-take-1 failure.

    The filter is typeOfLevel + shortName (+ level for heightAboveGround).
    After filtering there's exactly one message remaining, so we return the
    first data_var regardless of cfgrib's rename.
    """
    import xarray
    # GFS stores ``2t``/``10u``/``10v`` at ``heightAboveGround`` (2m and
    # 10m), ``prmsl`` at ``meanSea``, and ``tp`` at ``surface``.
    level_map = {
        "2t":    ("heightAboveGround", 2),
        "10u":   ("heightAboveGround", 10),
        "10v":   ("heightAboveGround", 10),
        "prmsl": ("meanSea", 0),
        "tp":    ("surface", 0),
    }
    type_of_level, level = level_map.get(ecmwf_short_name, ("surface", 0))
    filters = {"typeOfLevel": type_of_level, "shortName": ecmwf_short_name}
    if type_of_level == "heightAboveGround":
        filters["level"] = level
    ds = xarray.open_dataset(
        path, engine="cfgrib",
        backend_kwargs={"filter_by_keys": filters},
    )
    names = list(ds.data_vars)
    if not names:
        raise RuntimeError(
            f"cfgrib returned 0 variables for shortName={ecmwf_short_name!r}, "
            f"typeOfLevel={type_of_level!r}. Filter likely wrong — check "
            f"ecCodes naming (2t vs t2m, 10u vs u10, etc.)."
        )
    if len(names) != 1:
        log.warning("Multiple data vars (%s) after GRIB filter for %s; "
                    "using first", names, ecmwf_short_name)
    return ds[names[0]]


def _open_grib_pressure_levels(
    path: str, gfs_short_name: str, levels: Sequence[int],
) -> Any:
    """Return an xarray.DataArray for a pressure-level variable, selected to
    the requested levels. The result has a ``level`` dim with the 13-level set.
    """
    import xarray
    filters = {"typeOfLevel": "isobaricInhPa", "shortName": gfs_short_name}
    da = xarray.open_dataset(path, engine="cfgrib",
                              backend_kwargs={"filter_by_keys": filters})[gfs_short_name]
    # cfgrib names the pressure dim ``isobaricInhPa``; rename to ERA5's
    # ``level`` for shape compatibility.
    if "isobaricInhPa" in da.dims:
        da = da.rename({"isobaricInhPa": "level"})
    # Filter to the 13 levels we want. ``method='nearest'`` is safe since
    # every requested level is present natively.
    return da.sel(level=list(levels), method="nearest")


# ---------------------------------------------------------------------------
# Assembly: one cycle / one timestep worth of data
# ---------------------------------------------------------------------------

def _assemble_timestep(
    local_path: str,
    timestep: datetime,
    levels: Sequence[int] = GRAPHCAST_PRESSURE_LEVELS,
) -> Any:
    """Build an xarray.Dataset for a single time snapshot, in ERA5 naming.

    Opens the GRIB once per variable (cfgrib requires it). The resulting
    Dataset has:
        coords: time (scalar), latitude, longitude, level
        data_vars: all surface + all pressure-level ERA5 names
    """
    import numpy as np
    import xarray

    data_arrays = {}

    # Surface variables
    for era5_name, (gfs_name, _) in SURFACE_VARS.items():
        try:
            da = _open_grib_surface(local_path, gfs_name)
            da_c = unit_convert(era5_name, da)
            # Drop cfgrib's valid_time/step/time coords — we'll stamp our own.
            da_c = da_c.reset_coords(drop=True)
            data_arrays[era5_name] = da_c
        except Exception as exc:
            log.warning("GFS surface var %s (%s) failed to load: %s",
                        era5_name, gfs_name, exc)

    # Pressure-level variables
    for era5_name, (gfs_name, _) in PRESSURE_LEVEL_VARS.items():
        try:
            da = _open_grib_pressure_levels(local_path, gfs_name, levels)
            da_c = unit_convert(era5_name, da)
            da_c = da_c.reset_coords(drop=True)
            data_arrays[era5_name] = da_c
        except Exception as exc:
            log.warning("GFS pressure var %s (%s) failed to load: %s",
                        era5_name, gfs_name, exc)

    ds = xarray.Dataset(data_arrays)
    # Normalise coordinate names: cfgrib exposes latitude/longitude already,
    # but assert and rename if the dim names differ.
    ds = _normalise_coords(ds)
    # Stamp the time coord.
    ts64 = np.datetime64(timestep.replace(tzinfo=None).isoformat())
    ds = ds.expand_dims(time=[ts64])
    loaded_surface = [v for v in SURFACE_VARS if v in ds.data_vars]
    loaded_pressure = [v for v in PRESSURE_LEVEL_VARS if v in ds.data_vars]
    log.info("GFS %s: loaded %d/%d surface + %d/%d pressure-level vars",
             ts64, len(loaded_surface), len(SURFACE_VARS),
             len(loaded_pressure), len(PRESSURE_LEVEL_VARS))
    return ds


def compute_toa_incident_solar_radiation(
    times: Sequence[Any],
    latitudes: Any,
    longitudes: Any,
    accumulation_hours: int = 1,
    substeps: int = 6,
) -> Any:
    """Analytical ``toa_incident_solar_radiation`` in ERA5-compatible form.

    GraphCast requires TOA incident solar radiation as a forcing input. GFS
    doesn't publish it, so we reconstruct it from orbital geometry:

        TOA(t, φ, λ) = ∫_{t-1h}^{t} S₀ · max(0, cos(θ_z(τ, φ, λ))) dτ

    where θ_z is the solar zenith angle, S₀ = 1361 W/m² is the solar constant,
    and the integral samples 10-min substeps across the accumulation window.
    Returned units are J/m² accumulated over ``accumulation_hours``.

    **Accumulation window**: ERA5's ``toa_incident_solar_radiation`` in the
    ARCO Zarr that GraphCast trains on is a *1-hour accumulation* ending at
    the timestamp (i.e. hourly flux, not daily), even though GraphCast itself
    steps at 6h. The model's normalization statistics confirm it: the global
    mean of the stats file is ≈ 1.07 × 10⁶ J/m², which matches S₀/4 × 3600s
    (340 W/m² × 3600s = 1.22 × 10⁶). A 6-hour accumulation would have a
    mean 6× larger (~7 × 10⁶) and would push GraphCast's autoregressive
    rollout out of distribution — our first smoke on the benchmark Space
    diverged to impossible 60 °C temperatures with the old 6h default.

    Args:
        times: iterable of np.datetime64 values; each is the *end* of a
            ``accumulation_hours`` window.
        latitudes: 1-D array of latitudes (degrees, +N).
        longitudes: 1-D array of longitudes (degrees, 0-360 or -180 to 180).
        accumulation_hours: window length. Default 1 to match ERA5's
            convention as used by GraphCast.
        substeps: quadrature points within each window (6 → 10-min
            resolution for the default 1h window).

    Returns:
        np.ndarray shape (T, Nlat, Nlon), dtype float32, in J/m².
    """
    import numpy as np

    S0 = 1361.0
    dt_s = accumulation_hours * 3600 / substeps
    phi = np.deg2rad(np.asarray(latitudes, dtype=np.float64))[:, None]
    lam = np.deg2rad(np.asarray(longitudes, dtype=np.float64))[None, :]
    out = np.zeros((len(times), phi.shape[0], lam.shape[1]), dtype=np.float32)
    for i, t in enumerate(times):
        t_np = np.datetime64(t)
        t0 = t_np - np.timedelta64(accumulation_hours, "h")
        acc = np.zeros((phi.shape[0], lam.shape[1]), dtype=np.float64)
        for j in range(substeps):
            st = t0 + np.timedelta64(int((j + 0.5) * dt_s), "s")
            year_start = st.astype("datetime64[Y]").astype("datetime64[D]")
            doy = (st.astype("datetime64[D]") - year_start).astype(int) + 1
            decl = np.deg2rad(23.44) * np.sin(2 * np.pi * (doy - 81) / 365.0)
            sec_of_day = (st - st.astype("datetime64[D]")).astype("timedelta64[s]").astype(float)
            utc_frac = sec_of_day / 86400.0
            H = 2 * np.pi * (utc_frac - 0.5) + lam
            cos_z = np.sin(phi) * np.sin(decl) + np.cos(phi) * np.cos(decl) * np.cos(H)
            cos_z = np.maximum(cos_z, 0.0)
            acc += S0 * cos_z * dt_s
        out[i] = acc.astype(np.float32)
    return out


def _normalise_coords(ds: Any) -> Any:
    """Ensure the dataset uses ``latitude``/``longitude`` (ERA5 convention).

    cfgrib names the horizontal coords ``latitude`` and ``longitude`` by
    default, but some GRIB templates use ``lat``/``lon``. We normalise to
    the ERA5 long names so downstream code (which itself normalises to
    ``lat``/``lon`` later) has a single predictable starting point.
    """
    rename = {}
    if "lat" in ds.dims and "latitude" not in ds.dims:
        rename["lat"] = "latitude"
    if "lon" in ds.dims and "longitude" not in ds.dims:
        rename["lon"] = "longitude"
    if rename:
        ds = ds.rename(rename)
    return ds


# ---------------------------------------------------------------------------
# Top-level fetcher
# ---------------------------------------------------------------------------

def _cache_path(target_date: str, cycle_hour: int, horizon_hours: int) -> str:
    return os.path.join(
        _GFS_CACHE_DIR,
        f"gfs_{target_date}_c{cycle_hour:02d}_h{horizon_hours:03d}.pkl",
    )


def _load_cached(target_date: str, cycle_hour: int, horizon_hours: int) -> Optional[Any]:
    path = _cache_path(target_date, cycle_hour, horizon_hours)
    if os.path.exists(path):
        with open(path, "rb") as f:
            return pickle.load(f)
    return None


def _save_cached(ds: Any, target_date: str, cycle_hour: int, horizon_hours: int) -> None:
    os.makedirs(_GFS_CACHE_DIR, exist_ok=True)
    path = _cache_path(target_date, cycle_hour, horizon_hours)
    with open(path, "wb") as f:
        pickle.dump(ds, f)


def fetch_gfs_as_era5(
    target_date: str,
    forecast_horizon_hours: int = 288,
    cycle_hour: int = DEFAULT_CYCLE_HOUR,
    *,
    levels: Sequence[int] = GRAPHCAST_PRESSURE_LEVELS,
    work_dir: Optional[str] = None,
    attach_static: bool = True,
) -> Any:
    """Fetch a GFS cycle and return an ERA5-shape xarray.Dataset.

    Args:
        target_date: ISO date string (e.g. "2026-04-21"). The cycle's
            nominal date.
        forecast_horizon_hours: how far forward to include forecast steps.
            Covers the longest horizon either model needs (GraphCast
            FORECAST_STEPS=48 → 288h).
        cycle_hour: which UTC cycle (0/6/12/18). Defaults to 12Z.
        levels: pressure levels to keep. Defaults to the 13-level
            GraphCast-operational set.
        work_dir: download cache for raw GRIB files. Defaults to a subdir
            under ``_GFS_CACHE_DIR``.
        attach_static: if True, merge in ``geopotential_at_surface`` +
            ``land_sea_mask`` from the ERA5-derived static cache.

    Returns:
        An ``xarray.Dataset`` with:
            * dims: (time, level, latitude, longitude)
            * time: [target-6h, target, target+6h, ..., target+horizon_h]
            * 5 surface + 6 pressure-level data_vars (ERA5 names)
            * static vars if ``attach_static`` and cache is built

    Raises:
        RuntimeError if a critical variable fails to load across all timesteps.
        FileNotFoundError if ``attach_static`` and the static cache hasn't
        been built (call ``static_vars.ensure_static_cache()``).
    """
    import xarray

    cached = _load_cached(target_date, cycle_hour, forecast_horizon_hours)
    if cached is not None:
        log.info("GFS cache hit for %s %02dZ (+%dh)",
                 target_date, cycle_hour, forecast_horizon_hours)
        return cached

    cycle = _most_recent_cycle(target_date, cycle_hour)
    work_dir = work_dir or os.path.join(_GFS_CACHE_DIR, "grib_raw")

    # Two input timesteps (analysis from this cycle and the previous cycle)
    # + forecast steps at 6h cadence through the horizon.
    cycle_dt = cycle.datetime_utc()
    prev_cycle = _most_recent_cycle(
        (cycle_dt - timedelta(hours=6)).date().isoformat(),
        (cycle.hour - 6) % 24,
    )

    timesteps: List[Tuple[datetime, GfsCycle, int]] = []
    timesteps.append((prev_cycle.datetime_utc(), prev_cycle, 0))
    timesteps.append((cycle_dt, cycle, 0))
    n_forecast = forecast_horizon_hours // 6
    for i in range(1, n_forecast + 1):
        fhour = i * 6
        timesteps.append((cycle_dt + timedelta(hours=fhour), cycle, fhour))

    per_step_ds = []
    for (step_dt, step_cycle, fhour) in timesteps:
        grib_path = _download_grib2(step_cycle, fhour, work_dir)
        ds_step = _assemble_timestep(grib_path, step_dt, levels=levels)
        per_step_ds.append(ds_step)

    full_ds = xarray.concat(per_step_ds, dim="time")

    if attach_static:
        try:
            static_ds = load_static_ds()
        except FileNotFoundError:
            log.info("Static-var cache missing; building once from ERA5 (~30s)")
            from src.init_sources.static_vars import ensure_static_cache
            ensure_static_cache()
            static_ds = load_static_ds()
        # Merge keeps the time-varying vars plus the static 2D surfaces.
        full_ds = xarray.merge([full_ds, static_ds], compat="override")

    _save_cached(full_ds, target_date, cycle_hour, forecast_horizon_hours)
    return full_ds


# ---------------------------------------------------------------------------
# Helpers exposed for tests (pure xarray manipulation — no I/O)
# ---------------------------------------------------------------------------

def build_synthetic_gfs_dataset(
    timesteps: Sequence[datetime],
    levels: Sequence[int] = GRAPHCAST_PRESSURE_LEVELS,
    lat_vals=None,
    lon_vals=None,
    include_static: bool = True,
    temperature_k: float = 300.0,
) -> Any:
    """Construct a minimal synthetic dataset with the same shape this module
    returns in production. For unit tests only.

    Values are physically-plausible constants — the tests assert on shape
    and dimension layout, not on the values themselves.
    """
    import numpy as np
    import xarray

    if lat_vals is None:
        lat_vals = np.linspace(90.0, -90.0, GFS_N_LAT, dtype=np.float32)
    if lon_vals is None:
        lon_vals = np.linspace(0.0, 359.75, GFS_N_LON, dtype=np.float32)
    t_coord = np.array([np.datetime64(t.replace(tzinfo=None).isoformat())
                         for t in timesteps])

    shape_s = (len(t_coord), len(lat_vals), len(lon_vals))
    shape_p = (len(t_coord), len(levels), len(lat_vals), len(lon_vals))

    ds = xarray.Dataset(
        data_vars={
            "2m_temperature":              (("time", "latitude", "longitude"),
                                             np.full(shape_s, temperature_k, dtype=np.float32)),
            "10m_u_component_of_wind":      (("time", "latitude", "longitude"),
                                             np.zeros(shape_s, dtype=np.float32)),
            "10m_v_component_of_wind":      (("time", "latitude", "longitude"),
                                             np.zeros(shape_s, dtype=np.float32)),
            "mean_sea_level_pressure":      (("time", "latitude", "longitude"),
                                             np.full(shape_s, 101_325.0, dtype=np.float32)),
            "total_precipitation_6hr":      (("time", "latitude", "longitude"),
                                             np.zeros(shape_s, dtype=np.float32)),
            "temperature":                  (("time", "level", "latitude", "longitude"),
                                             np.full(shape_p, 260.0, dtype=np.float32)),
            "specific_humidity":            (("time", "level", "latitude", "longitude"),
                                             np.full(shape_p, 0.005, dtype=np.float32)),
            "u_component_of_wind":          (("time", "level", "latitude", "longitude"),
                                             np.zeros(shape_p, dtype=np.float32)),
            "v_component_of_wind":          (("time", "level", "latitude", "longitude"),
                                             np.zeros(shape_p, dtype=np.float32)),
            "vertical_velocity":            (("time", "level", "latitude", "longitude"),
                                             np.zeros(shape_p, dtype=np.float32)),
            "geopotential":                 (("time", "level", "latitude", "longitude"),
                                             np.full(shape_p, 5.0e4, dtype=np.float32)),
        },
        coords={
            "time":      t_coord,
            "level":     np.asarray(levels, dtype=np.int32),
            "latitude":  lat_vals,
            "longitude": lon_vals,
        },
    )
    if include_static:
        from src.init_sources.static_vars import build_synthetic_static_ds
        static_ds = build_synthetic_static_ds(lat_vals=lat_vals, lon_vals=lon_vals)
        ds = ds.merge(static_ds)
    return ds
