"""Static (time-invariant) variables for GraphCast / GenCast init.

GraphCast requires two static fields that GFS's standard pgrb2 products do
not ship: ``geopotential_at_surface`` (surface elevation × g, used to place
the model on Earth's terrain) and ``land_sea_mask`` (binary land/water flag).

They are pulled once from ERA5 and cached to disk as a small netCDF. GFS
inits then attach them verbatim — the values don't change per init.

The cache lives at ``data/init_sources/era5_static.nc`` (committed to the
repo). If it's missing, the ``ensure_static_cache`` helper downloads a fresh
copy from ARCO ERA5. That download is a one-time, ~5 MB pull (two 721×1440
float32 surfaces + coords).

Phase 1 note: the cache file is not generated in this commit — Phase 2 will
produce it the first time the integration runs. The loader here is wired
end-to-end so Phase 2 can simply invoke ``load_static_ds()`` without further
work.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

# Path to the static-variable cache. Relative to the repo root so both local
# dev and HF Space runs find it in the same place.
DEFAULT_CACHE_PATH = str(
    Path(__file__).resolve().parent.parent.parent
    / "data" / "init_sources" / "era5_static.nc"
)

STATIC_VARS_NEEDED = ("geopotential_at_surface", "land_sea_mask")


def cache_path() -> str:
    return os.environ.get("GFS_STATIC_CACHE", DEFAULT_CACHE_PATH)


def cache_exists() -> bool:
    return os.path.exists(cache_path())


def load_static_ds() -> Any:
    """Load the static-variable netCDF as an xarray.Dataset.

    Raises FileNotFoundError if the cache hasn't been built yet. Callers in
    Phase 2 should either call ``ensure_static_cache()`` first or fall back
    gracefully (GraphCast's existing code zero-fills missing static vars
    with a warning — same behavior preserved here).
    """
    import xarray  # lazy — module is importable without xarray present
    path = cache_path()
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Static-variable cache not found at {path}. "
            f"Run ensure_static_cache() to build it from ERA5, or unset "
            f"GFS_STATIC_CACHE to use the default repo path."
        )
    return xarray.load_dataset(path)


def ensure_static_cache(force: bool = False) -> str:
    """Build the static-variable cache from ERA5 if it doesn't exist.

    Returns the path to the cache file. Idempotent.

    This fetches a single ERA5 timestep's static fields from the ARCO Zarr.
    ERA5 writes the same static values at every timestep (they truly don't
    change), so any valid time works — we use 2024-01-01 as a stable anchor.
    """
    import xarray
    path = cache_path()
    if os.path.exists(path) and not force:
        return path

    os.makedirs(os.path.dirname(path), exist_ok=True)

    era5_path = "gs://gcp-public-data-arco-era5/ar/full_37-1h-0p25deg-chunk-1.zarr-v3"
    full_ds = xarray.open_zarr(
        era5_path, chunks=None, storage_options={"token": "anon"},
        consolidated=True,
    )
    # Pick a known-valid timestep; values are static so the exact time is moot.
    import numpy as np
    t_anchor = np.datetime64("2024-01-01T12:00")
    t_sel = full_ds.time.sel(time=t_anchor, method="nearest").values

    vars_present = [v for v in STATIC_VARS_NEEDED if v in full_ds.data_vars]
    if not vars_present:
        raise RuntimeError(
            f"ERA5 Zarr at {era5_path} lacks {STATIC_VARS_NEEDED}. "
            f"Check the upstream bucket — this would be a schema change "
            f"upstream, not a bug here."
        )
    static_ds = full_ds[vars_present].sel(time=t_sel).compute()
    # Drop the time dim (static vars have no real time axis even though ERA5
    # ships them per-step).
    if "time" in static_ds.dims:
        static_ds = static_ds.drop_vars("time")
    elif "time" in static_ds.coords:
        static_ds = static_ds.drop_vars("time")

    static_ds.to_netcdf(path)
    return path


def build_synthetic_static_ds(
    lat_vals=None, lon_vals=None,
):
    """Build a tiny synthetic static dataset for use in unit tests.

    Returns a two-variable xarray.Dataset with plausible values — zeros for
    ocean, a constant hill for land — on whatever grid is passed in. No
    pretensions to realism; the tests only care that downstream code can
    read and shape-check the fields.
    """
    import numpy as np
    import xarray
    if lat_vals is None:
        lat_vals = np.linspace(90.0, -90.0, 721, dtype=np.float32)
    if lon_vals is None:
        lon_vals = np.linspace(0.0, 359.75, 1440, dtype=np.float32)

    shape = (len(lat_vals), len(lon_vals))
    gp_surf = np.full(shape, 0.0, dtype=np.float32)
    lsm = np.zeros(shape, dtype=np.float32)
    # Mark the India region as land for a sanity check: lat 8-14 N, lon 74-80 E.
    lat_mask = (lat_vals >= 8.0) & (lat_vals <= 14.0)
    lon_mask = (lon_vals >= 74.0) & (lon_vals <= 80.0)
    if lat_mask.any() and lon_mask.any():
        lsm[np.ix_(lat_mask, lon_mask)] = 1.0
        gp_surf[np.ix_(lat_mask, lon_mask)] = 500.0 * 9.80665  # ~500m elev

    return xarray.Dataset(
        {
            "geopotential_at_surface": (("latitude", "longitude"), gp_surf),
            "land_sea_mask":           (("latitude", "longitude"), lsm),
        },
        coords={"latitude": lat_vals, "longitude": lon_vals},
    )
