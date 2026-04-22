"""Init-source plumbing for GraphCast / GenCast.

The existing production pipeline opens ARCO ERA5 Zarr directly from inside
``graphcast_client._fetch_era5_sync`` and ``gencast_client._prepare_era5_inputs``.
ERA5T has a ~5-day lag, which means every operational forecast is actually at
lead 6-12 days — past the skillful regime for tropical 2m_temperature.

This package provides an alternative: GFS (NOAA Global Forecast System) analysis
at ~3h lag. A GFS-sourced ``xarray.Dataset`` is shape-compatible with the ERA5
Zarr downstream operations, so the integration in Phase 2 is a one-line source
swap behind a config toggle.

Phase 1 status: this package is reachable only from tests. Nothing in the
production pipeline imports it. Wiring is deferred to Phase 2 after head-to-head
validation.

Public entry point:
    fetch_gfs_as_era5(target_date: str) -> xarray.Dataset
"""

from __future__ import annotations

from src.init_sources.gfs import fetch_gfs_as_era5  # noqa: F401
