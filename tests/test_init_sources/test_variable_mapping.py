"""Tests for the GFS ↔ ERA5 variable mapping tables.

These are pure-data tests — no network, no cfgrib, no xarray I/O. They
protect against accidental breakage of the lookup tables that the GFS
fetcher in ``src/init_sources/gfs.py`` depends on.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.init_sources import variable_mapping as vm


class TestSurfaceVarsLookup:
    def test_all_surface_vars_return_short_name_and_scale(self):
        for era5_name, (short, (scale, offset)) in vm.SURFACE_VARS.items():
            assert isinstance(era5_name, str) and era5_name
            assert isinstance(short, str) and short
            assert isinstance(scale, float)
            assert isinstance(offset, float)

    def test_expected_surface_vars_present(self):
        # These 5 surface fields are load-bearing for GraphCast init.
        expected = {
            "2m_temperature", "10m_u_component_of_wind",
            "10m_v_component_of_wind", "mean_sea_level_pressure",
            "total_precipitation_6hr",
        }
        assert expected <= set(vm.SURFACE_VARS.keys()), (
            "Missing surface vars — GraphCast will refuse to init without them"
        )

    def test_precipitation_converts_mm_to_m(self):
        # GFS ``tp`` is kg/m² (≡ mm of liquid water); ERA5 is m.
        # 12 mm of rain → 0.012 m.
        scale, offset = vm.SURFACE_VARS["total_precipitation_6hr"][1]
        assert scale == pytest.approx(1e-3)
        assert offset == 0.0

    def test_temperature_is_already_kelvin(self):
        # Both GFS and ERA5 ship t2m in Kelvin — no conversion.
        scale, offset = vm.SURFACE_VARS["2m_temperature"][1]
        assert scale == 1.0
        assert offset == 0.0


class TestPressureLevelVarsLookup:
    def test_geopotential_converts_gpm_to_m2s2(self):
        # GFS `gh` is geopotential HEIGHT in geopotential metres; ERA5
        # stores geopotential (height × g) in m²/s². Check the scale is g.
        scale, offset = vm.PRESSURE_LEVEL_VARS["geopotential"][1]
        assert scale == pytest.approx(9.80665)
        assert offset == 0.0

    def test_six_pressure_level_variables_present(self):
        expected = {
            "temperature", "specific_humidity", "u_component_of_wind",
            "v_component_of_wind", "vertical_velocity", "geopotential",
        }
        assert expected <= set(vm.PRESSURE_LEVEL_VARS.keys())


class TestPressureLevelsSelection:
    def test_graphcast_has_13_canonical_levels(self):
        assert len(vm.GRAPHCAST_PRESSURE_LEVELS) == 13

    def test_levels_in_descending_model_atmosphere(self):
        # GraphCast and GenCast list their levels ascending in pressure
        # (top of atmosphere → surface). 50 .. 1000 hPa strictly increasing.
        levels = list(vm.GRAPHCAST_PRESSURE_LEVELS)
        assert levels == sorted(levels), "levels must be ascending pressure"
        assert min(levels) >= 50, "lowest level must be ≥ 50 hPa"
        assert max(levels) <= 1000, "highest level must be ≤ 1000 hPa"

    def test_levels_available_in_gfs_pgrb2_native(self):
        # GFS pgrb2.0p25 natively provides these levels. If any GraphCast
        # level isn't in this list, the select-to-13 step would need to
        # interpolate instead of just subsetting.
        gfs_native = {
            10, 20, 30, 40, 50, 70, 100, 150, 200, 250, 300, 350, 400, 450,
            500, 550, 600, 650, 700, 750, 800, 850, 900, 925, 950, 975, 1000,
        }
        assert set(vm.GRAPHCAST_PRESSURE_LEVELS) <= gfs_native


class TestHelpers:
    def test_gfs_short_name_surface(self):
        assert vm.gfs_short_name("2m_temperature") == "t2m"
        assert vm.gfs_short_name("mean_sea_level_pressure") == "prmsl"

    def test_gfs_short_name_pressure_level(self):
        assert vm.gfs_short_name("temperature") == "t"
        assert vm.gfs_short_name("geopotential") == "gh"

    def test_gfs_short_name_raises_on_unknown(self):
        with pytest.raises(KeyError):
            vm.gfs_short_name("not_a_variable")

    def test_unit_convert_temperature_is_identity(self):
        xs = np.array([270.0, 290.0, 310.0], dtype=np.float32)
        ys = vm.unit_convert("2m_temperature", xs)
        np.testing.assert_allclose(ys, xs)

    def test_unit_convert_precipitation_mm_to_m(self):
        mm = np.array([0.0, 5.0, 12.5], dtype=np.float32)
        meters = vm.unit_convert("total_precipitation_6hr", mm)
        np.testing.assert_allclose(meters, [0.0, 0.005, 0.0125], rtol=1e-5)

    def test_unit_convert_geopotential_applies_g(self):
        gpm = np.array([0.0, 5000.0, 10_000.0], dtype=np.float32)
        m2s2 = vm.unit_convert("geopotential", gpm)
        np.testing.assert_allclose(
            m2s2, [0.0, 5000.0 * 9.80665, 10_000.0 * 9.80665], rtol=1e-6
        )

    def test_all_era5_names_union(self):
        names = vm.all_era5_names()
        assert set(names) == set(vm.SURFACE_VARS) | set(vm.PRESSURE_LEVEL_VARS)
