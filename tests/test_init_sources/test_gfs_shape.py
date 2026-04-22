"""Shape + interface tests for the GFS init source.

These tests use a synthetic xarray.Dataset built by
``gfs.build_synthetic_gfs_dataset`` — they never hit the network and do not
require cfgrib/eccodes. The assertion surface is the SAME set of downstream
operations that ``graphcast_client._fetch_era5_sync`` and
``gencast_client._prepare_era5_inputs`` perform on the ERA5 ``full_ds``:

    * ``.time.sel(time=X, method='nearest')``
    * ``.sel(time=[t0, t1])``
    * variable access by ERA5 canonical name
    * ``.sel(level=[...])`` on pressure-level vars
    * ``.compute()`` — even if the dataset isn't Dask-backed, existing code
      still calls it, so the Dataset must accept it.

If Phase 2 wires this module into the pipeline and anything here breaks,
we'd have a merge/rename bug. These tests catch that before the Space run.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest
import xarray

from src.init_sources import gfs
from src.init_sources.variable_mapping import (
    GRAPHCAST_PRESSURE_LEVELS,
    PRESSURE_LEVEL_VARS,
    STATIC_VARS,
    SURFACE_VARS,
)


def _make_timesteps(n: int = 4, step_hours: int = 6):
    t0 = datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc)
    return [t0 + timedelta(hours=i * step_hours) for i in range(n)]


def _small_grid_dataset(include_static=True):
    """Build a small-grid synthetic dataset (fast tests)."""
    lat_vals = np.linspace(14.0, 8.0, 25, dtype=np.float32)      # Kerala band
    lon_vals = np.linspace(74.0, 80.0, 25, dtype=np.float32)     # TN band
    return gfs.build_synthetic_gfs_dataset(
        timesteps=_make_timesteps(n=4),
        lat_vals=lat_vals,
        lon_vals=lon_vals,
        include_static=include_static,
    )


class TestSyntheticDatasetShape:
    def test_returns_xarray_dataset(self):
        ds = _small_grid_dataset()
        assert isinstance(ds, xarray.Dataset)

    def test_has_expected_dims(self):
        ds = _small_grid_dataset()
        for d in ("time", "level", "latitude", "longitude"):
            assert d in ds.dims, f"missing dim {d!r}"

    def test_time_dim_has_4_steps(self):
        ds = _small_grid_dataset()
        assert ds.sizes["time"] == 4

    def test_level_dim_matches_graphcast(self):
        ds = _small_grid_dataset()
        assert ds.sizes["level"] == len(GRAPHCAST_PRESSURE_LEVELS)
        np.testing.assert_array_equal(
            ds["level"].values,
            np.asarray(GRAPHCAST_PRESSURE_LEVELS, dtype=np.int32),
        )


class TestVariableCoverage:
    def test_all_surface_vars_present(self):
        ds = _small_grid_dataset()
        for era5_name in SURFACE_VARS:
            assert era5_name in ds.data_vars, f"missing surface var {era5_name!r}"

    def test_all_pressure_level_vars_present(self):
        ds = _small_grid_dataset()
        for era5_name in PRESSURE_LEVEL_VARS:
            assert era5_name in ds.data_vars, f"missing pressure var {era5_name!r}"

    def test_static_vars_attached_when_requested(self):
        ds = _small_grid_dataset(include_static=True)
        for s in STATIC_VARS:
            assert s in ds.data_vars, (
                f"static var {s!r} must be attached when include_static=True — "
                "GraphCast's task_config lists it in input_variables"
            )

    def test_static_vars_omitted_when_not_requested(self):
        ds = _small_grid_dataset(include_static=False)
        for s in STATIC_VARS:
            assert s not in ds.data_vars

    def test_pressure_level_vars_have_level_dim(self):
        ds = _small_grid_dataset()
        for era5_name in PRESSURE_LEVEL_VARS:
            assert "level" in ds[era5_name].dims, (
                f"{era5_name!r} must carry the level dim — downstream "
                ".sel(level=[...]) will otherwise raise"
            )

    def test_surface_vars_have_no_level_dim(self):
        ds = _small_grid_dataset()
        for era5_name in SURFACE_VARS:
            assert "level" not in ds[era5_name].dims, (
                f"{era5_name!r} must NOT carry the level dim — it's a "
                "single-level surface field"
            )

    def test_static_vars_have_no_time_or_level_dim(self):
        ds = _small_grid_dataset()
        for s in STATIC_VARS:
            assert "time" not in ds[s].dims
            assert "level" not in ds[s].dims


class TestDownstreamCompatibility:
    """Exercise the same xarray operations ``_fetch_era5_sync`` runs
    against the ERA5 ``full_ds``. If any of these break, Phase 2 wiring
    would blow up at runtime — we catch them here first.
    """

    def test_time_sel_nearest(self):
        ds = _small_grid_dataset()
        # existing code: ``full_ds.time.sel(time=target - 6h, method='nearest')``
        target = np.datetime64("2026-04-21T12:00")
        t1 = ds.time.sel(time=target, method="nearest").values
        assert t1 is not None

    def test_time_sel_list_of_two_timesteps(self):
        ds = _small_grid_dataset()
        # existing code: ``full_ds[dynamic_available].sel(time=input_times)``
        input_times = ds.time.values[:2].tolist()
        sub = ds.sel(time=input_times)
        assert sub.sizes["time"] == 2

    def test_level_subset_selection(self):
        ds = _small_grid_dataset()
        # existing code: ``full_ds[dynamic_available].sel(time=...,  level=sel_levels)``
        sel = ds["temperature"].sel(level=[500, 850, 1000])
        assert sel.sizes["level"] == 3

    def test_compute_is_callable_even_on_non_dask_dataset(self):
        ds = _small_grid_dataset()
        # existing code: ``ds_input = full_ds[...].sel(...).compute()``.
        computed = ds[["2m_temperature"]].sel(time=ds.time.values[0]).compute()
        assert "2m_temperature" in computed.data_vars

    def test_isnull_all_returns_bool_like(self):
        ds = _small_grid_dataset()
        # existing code: ``bool(ds_input[var].isnull().all().item())``
        all_nan = ds["2m_temperature"].isnull().all().item()
        assert isinstance(all_nan, (bool, np.bool_))
        assert all_nan is False or all_nan == 0  # synthetic data has no NaN

    def test_point_nearest_sel(self):
        ds = _small_grid_dataset()
        # existing code in _extract_station_forecasts:
        #   point = predictions.sel(lat=station.lat, lon=station.lon,
        #                             method='nearest')
        # except the returned ds uses 'latitude'/'longitude' (ERA5 names).
        # graphcast_client renames to lat/lon later via rename_map. We verify
        # both names work here so the rename step succeeds.
        kerala = ds.sel(latitude=8.5, longitude=76.95, method="nearest")
        assert kerala["2m_temperature"].size == ds.sizes["time"]


class TestGfsCycle:
    def test_datetime_utc_is_utc_aware(self):
        cyc = gfs.GfsCycle(date="2026-04-21", hour=12)
        dt = cyc.datetime_utc()
        assert dt.tzinfo is not None
        assert dt.year == 2026 and dt.month == 4 and dt.day == 21
        assert dt.hour == 12

    def test_s3_prefix_format(self):
        cyc = gfs.GfsCycle(date="2026-04-21", hour=6)
        assert cyc.s3_prefix() == "gfs.20260421/06/atmos"

    def test_file_name_analysis(self):
        cyc = gfs.GfsCycle(date="2026-04-21", hour=12)
        # f000 is the analysis (t=0 of the cycle).
        assert cyc.file_name(0) == "gfs.t12z.pgrb2.0p25.f000"

    def test_file_name_forecast_6h(self):
        cyc = gfs.GfsCycle(date="2026-04-21", hour=12)
        assert cyc.file_name(6) == "gfs.t12z.pgrb2.0p25.f006"

    def test_file_name_forecast_168h(self):
        cyc = gfs.GfsCycle(date="2026-04-21", hour=12)
        # 7-day forecast — end of GenCast's horizon.
        assert cyc.file_name(168) == "gfs.t12z.pgrb2.0p25.f168"

    def test_s3_key_composition(self):
        cyc = gfs.GfsCycle(date="2026-04-21", hour=12)
        assert cyc.s3_key(6) == "gfs.20260421/12/atmos/gfs.t12z.pgrb2.0p25.f006"


class TestCycleSelection:
    def test_default_cycle_is_12z(self):
        cyc = gfs._most_recent_cycle("2026-04-21")
        assert cyc.hour == 12

    def test_explicit_cycle_hour_respected(self):
        cyc = gfs._most_recent_cycle("2026-04-21", target_cycle_hour=0)
        assert cyc.hour == 0

    def test_non_canonical_cycle_hour_snaps_down(self):
        # Someone passes 9 UTC — GFS only runs 00/06/12/18, so we expect
        # the preceding 06Z cycle.
        cyc = gfs._most_recent_cycle("2026-04-21", target_cycle_hour=9)
        assert cyc.hour == 6


class TestPhysicalPlausibility:
    def test_synthetic_temperature_is_kelvin_valued(self):
        ds = _small_grid_dataset()
        # The synthetic fixture ships 300 K everywhere. Convert a few points
        # to Celsius and sanity-check the sign.
        t_c = ds["2m_temperature"].values - 273.15
        # 300 K → 26.85 °C; inside the plausible Earth-surface range.
        assert np.all(t_c > -50) and np.all(t_c < 60)

    def test_synthetic_mslp_in_physical_range_pa(self):
        ds = _small_grid_dataset()
        mslp = ds["mean_sea_level_pressure"].values
        # Earth MSLP lives in ~87000-108000 Pa. Synthetic fixture uses 101325.
        assert np.all(mslp > 80_000) and np.all(mslp < 110_000)

    def test_synthetic_precipitation_non_negative_in_metres(self):
        ds = _small_grid_dataset()
        tp = ds["total_precipitation_6hr"].values
        assert np.all(tp >= 0.0)
        # After the mm→m conversion, a realistic 6h max ≤ ~0.2 m (200mm).
        assert np.all(tp < 1.0)


class TestToaIncidentSolarRadiation:
    """GFS doesn't publish TOA so we reconstruct it analytically.

    GraphCast fails without TOA (it's a forcing variable). These tests lock in
    shape, sign, and physical magnitude so a regression surfaces before a
    live run.
    """

    def _basic_call(self, times, lats, lons):
        return gfs.compute_toa_incident_solar_radiation(
            times=times, latitudes=lats, longitudes=lons,
        )

    def test_shape_matches_T_Nlat_Nlon(self):
        times = [np.datetime64("2026-04-15T12:00"),
                 np.datetime64("2026-04-15T18:00"),
                 np.datetime64("2026-04-16T00:00")]
        lats = np.array([-10.0, 0.0, 10.0])
        lons = np.array([0.0, 90.0, 180.0, 270.0])
        out = self._basic_call(times, lats, lons)
        assert out.shape == (3, 3, 4)

    def test_all_nonnegative_and_finite(self):
        times = [np.datetime64("2026-04-15T12:00")]
        lats = np.linspace(-80, 80, 33)
        lons = np.linspace(0, 359, 37)
        out = self._basic_call(times, lats, lons)
        assert np.isfinite(out).all()
        assert (out >= 0).all()

    def test_night_window_is_zero_at_equator(self):
        # 00Z window = 9pm-3am local at λ=0; entirely dark at the equator.
        out = self._basic_call(
            [np.datetime64("2026-04-15T00:00")],
            [0.0], [0.0],
        )
        assert out[0, 0, 0] == 0.0

    def test_noon_window_peaks_near_solar_constant(self):
        # Default 1h accumulation (what GraphCast was trained on — see the
        # compute_toa_incident_solar_radiation docstring for why 1h not 6h).
        # Noon at equator, λ=0: cos(zenith) averages ~0.95 over the hour.
        # Peak 1h energy ≤ 3600 * 1361 = 4.9e6 J/m²; typical ~4e6.
        out = self._basic_call(
            [np.datetime64("2026-04-15T12:00")],
            [0.0], [0.0],
        )
        v = float(out[0, 0, 0])
        assert 2e6 < v < 5e6, f"noon-window TOA out of range: {v:.3e} J/m²"

    def test_graphcast_stats_compatibility(self):
        # GraphCast's published stats give mean toa_incident_solar_radiation
        # ≈ 1.07e6 J/m² (global/time average). Our values must land in the
        # same order of magnitude — a 6× error (the 6h bug) would push the
        # autoregressive rollout out of distribution and diverge.
        ts = [np.datetime64(f"2026-04-15T{h:02d}:00") for h in (0, 6, 12, 18)]
        lats = np.linspace(-87.5, 87.5, 36)
        lons = np.linspace(0, 355, 72)
        out = self._basic_call(ts, lats, lons)
        global_mean = float(out.mean())
        assert 5e5 < global_mean < 3e6, (
            f"mean TOA {global_mean:.3e} J/m² outside expected band around "
            f"GraphCast's 1.07e6; accumulation_hours may be wrong"
        )

    def test_polar_night_is_zero(self):
        # June 15: northern summer → south pole is in polar night.
        out = self._basic_call(
            [np.datetime64("2026-06-15T12:00")],
            [-85.0], [0.0],
        )
        assert out[0, 0, 0] == 0.0
