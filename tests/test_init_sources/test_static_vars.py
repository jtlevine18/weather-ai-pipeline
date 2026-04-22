"""Tests for the static-variable loader + synthetic builder."""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest
import xarray

from src.init_sources import static_vars


class TestSyntheticStaticDS:
    def test_has_both_static_vars(self):
        ds = static_vars.build_synthetic_static_ds()
        for name in static_vars.STATIC_VARS_NEEDED:
            assert name in ds.data_vars

    def test_full_0p25_grid_shape(self):
        ds = static_vars.build_synthetic_static_ds()
        assert ds.sizes["latitude"] == 721
        assert ds.sizes["longitude"] == 1440

    def test_small_grid_shape(self):
        lat = np.linspace(14.0, 8.0, 25, dtype=np.float32)
        lon = np.linspace(74.0, 80.0, 25, dtype=np.float32)
        ds = static_vars.build_synthetic_static_ds(lat_vals=lat, lon_vals=lon)
        assert ds.sizes["latitude"] == 25
        assert ds.sizes["longitude"] == 25

    def test_india_region_marked_as_land(self):
        ds = static_vars.build_synthetic_static_ds()
        lsm_india = ds["land_sea_mask"].sel(
            latitude=slice(14.0, 8.0), longitude=slice(74.0, 80.0)
        )
        # At least some India grid cells are land — sanity check the synthetic
        # setup, not a climatological claim.
        assert (lsm_india.values > 0).any()

    def test_static_ds_has_no_time_or_level_dims(self):
        ds = static_vars.build_synthetic_static_ds()
        assert "time" not in ds.dims
        assert "level" not in ds.dims


class TestCachePathResolution:
    def test_default_path_is_inside_repo(self):
        # The default resolves to data/init_sources/era5_static.nc under the
        # project root. Phase 2 will build it on first use.
        p = static_vars.cache_path()
        assert p.endswith(os.path.join("data", "init_sources", "era5_static.nc")), p

    def test_env_var_override(self, tmp_path, monkeypatch):
        override = str(tmp_path / "static_override.nc")
        monkeypatch.setenv("GFS_STATIC_CACHE", override)
        assert static_vars.cache_path() == override


class TestLoadStaticDS:
    def test_raises_helpfully_when_cache_missing(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GFS_STATIC_CACHE", str(tmp_path / "nope.nc"))
        with pytest.raises(FileNotFoundError):
            static_vars.load_static_ds()

    def test_loads_a_round_tripped_cache(self, tmp_path, monkeypatch):
        # Build a synthetic cache, write to disk, verify the loader reads it.
        cache_path = tmp_path / "fake_static.nc"
        monkeypatch.setenv("GFS_STATIC_CACHE", str(cache_path))

        ds = static_vars.build_synthetic_static_ds(
            lat_vals=np.array([10.0, 0.0], dtype=np.float32),
            lon_vals=np.array([77.0, 80.0], dtype=np.float32),
        )
        ds.to_netcdf(cache_path)

        loaded = static_vars.load_static_ds()
        for name in static_vars.STATIC_VARS_NEEDED:
            assert name in loaded.data_vars
        np.testing.assert_array_equal(
            loaded["land_sea_mask"].values, ds["land_sea_mask"].values
        )
