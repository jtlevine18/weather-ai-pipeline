"""Live GFS integration test — skipped by default.

This is the "does the module actually work against real AWS GFS data" check.
It runs only when ``GFS_LIVE_TEST=1`` is set, because it requires:

    * network access to ``noaa-gfs-bdp-pds`` on S3 (public bucket, unsigned)
    * ``cfgrib`` installed (pulls in the eccodes C library)
    * ``boto3`` for the S3 fetch
    * ~200 MB of disk for one GRIB2 file

Sanity-check assertions are conservative: if cfgrib or boto3 are missing we
``pytest.skip`` instead of failing so the suite stays green on machines
without the deps.

Run manually:

    GFS_LIVE_TEST=1 .venv/bin/pytest -q -k live tests/test_init_sources/test_gfs_live.py
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import os
import tempfile

import numpy as np
import pytest

from src.init_sources import gfs
from src.init_sources.variable_mapping import GRAPHCAST_PRESSURE_LEVELS


REQUIRED_PACKAGES = ("cfgrib", "boto3")


def _required_deps_present() -> bool:
    return all(importlib.util.find_spec(pkg) is not None for pkg in REQUIRED_PACKAGES)


pytestmark = pytest.mark.skipif(
    os.environ.get("GFS_LIVE_TEST") != "1",
    reason="set GFS_LIVE_TEST=1 to run live AWS/cfgrib integration tests",
)


def _skip_if_no_deps():
    if not _required_deps_present():
        pytest.skip(f"install {REQUIRED_PACKAGES} to run live GFS tests")


@pytest.mark.live
def test_download_one_grib_file(tmp_path):
    """Smallest-possible live test: pull one GRIB2 file and verify it exists."""
    _skip_if_no_deps()

    # Use yesterday 06Z — old enough that the cycle is definitely complete.
    yesterday = (dt.datetime.utcnow().date() - dt.timedelta(days=1)).isoformat()
    cycle = gfs.GfsCycle(date=yesterday, hour=6)

    path = gfs._download_grib2(cycle, forecast_hour=0, dest_dir=str(tmp_path))
    assert os.path.exists(path)
    assert os.path.getsize(path) > 10_000_000, (
        "GFS pgrb2.0p25 f000 files are hundreds of MB; <10MB suggests partial download"
    )


@pytest.mark.live
def test_fetch_gfs_as_era5_assembles_dataset(tmp_path, monkeypatch):
    """End-to-end: fetch + parse + assemble the first two timesteps, check shape."""
    _skip_if_no_deps()

    # Point the cache at a tmp dir so this test doesn't pollute /tmp.
    monkeypatch.setattr(gfs, "_GFS_CACHE_DIR", str(tmp_path))

    yesterday = (dt.datetime.utcnow().date() - dt.timedelta(days=1)).isoformat()

    # Keep the forecast horizon tiny so the live test completes in reasonable
    # time — only 12 hours out (3 timesteps total: -6h analysis, 0h analysis,
    # +6h forecast). The shape/variable coverage is the same regardless of
    # horizon, so 12h is sufficient signal for the live sanity check.
    ds = gfs.fetch_gfs_as_era5(
        target_date=yesterday,
        forecast_horizon_hours=12,
        cycle_hour=6,
        work_dir=str(tmp_path / "grib_raw"),
        attach_static=False,
    )

    # Shape checks
    assert ds.sizes["latitude"] == gfs.GFS_N_LAT
    assert ds.sizes["longitude"] == gfs.GFS_N_LON
    assert ds.sizes["level"] == len(GRAPHCAST_PRESSURE_LEVELS)
    assert ds.sizes["time"] >= 3  # prev cycle t0, current t0, +6h forecast

    # Variable coverage — at least 2m_temp + one pressure-level must load.
    assert "2m_temperature" in ds.data_vars
    assert "temperature" in ds.data_vars

    # Physical plausibility on a Kerala grid cell.
    t2m = ds["2m_temperature"].sel(
        latitude=8.5, longitude=77.0, method="nearest"
    ).values
    # Kelvin; South India is never < 273 K (0 °C) even at night.
    assert (t2m > 273).all() and (t2m < 320).all(), (
        f"2m_temperature at Kerala grid cell {t2m} out of plausible K range"
    )
