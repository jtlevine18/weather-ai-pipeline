"""GFS → ERA5 variable name, unit, and pressure-level conversion tables.

These are pure data. Tests exercise them directly. The fetcher in gfs.py
consumes them.

ERA5 (via ARCO Zarr, what GraphCast + GenCast are trained on) uses long
human-readable names: ``2m_temperature``, ``10m_u_component_of_wind``, etc.
GFS GRIB2 uses short codes: ``t2m``, ``u10``, etc. Both encode the same
physical quantities but with different conventions.

Everything here is single-source-of-truth: if GFS introduces a new short-code
convention, it only gets added here and the fetcher picks it up automatically.
"""

from __future__ import annotations

from typing import Dict, Tuple


# ---------------------------------------------------------------------------
# Surface variables (single-level)
# ---------------------------------------------------------------------------

# Each entry: ERA5 canonical name → (GFS cfgrib short-name, unit conversion)
# Unit conversion is a (scale, offset) tuple applied as gfs_value * scale + offset.
# When no conversion is needed (same units), use (1.0, 0.0).
#
# GFS units from cfgrib:
#   t2m:  K      (matches ERA5)
#   u10:  m/s    (matches ERA5)
#   v10:  m/s    (matches ERA5)
#   prmsl:Pa     (matches ERA5)
#   tp:   kg/m^2 (≡ mm of liquid water, ERA5 has m — divide by 1000)
#
# GFS GRIB2 has total_precipitation as an accumulated quantity over the forecast
# step — cfgrib exposes ``tp`` in kg/m² which is numerically the same as mm of
# liquid water. ERA5 reports precipitation in m. We divide by 1000 to match.

#
# ``ecCodes`` shortName differs from cfgrib's output variable name for a
# handful of surface fields. The GRIB *message* is indexed by the ecCodes
# shortName (``2t``, ``10u``, ``10v``, ``prmsl``, ``tp``) which is what
# ``filter_by_keys`` takes. When cfgrib materialises the filtered message as
# an xarray variable, it uses its own naming (``t2m``, ``u10``, ``v10``,
# ``prmsl``, ``tp``). We carry the ecCodes shortName here because the filter
# is load-bearing — get this wrong and filter_by_keys returns an empty
# dataset, which was the Phase-2-take-1 failure mode.

SURFACE_VARS: Dict[str, Tuple[str, Tuple[float, float]]] = {
    "2m_temperature":               ("2t",    (1.0,    0.0)),
    "10m_u_component_of_wind":      ("10u",   (1.0,    0.0)),
    "10m_v_component_of_wind":      ("10v",   (1.0,    0.0)),
    "mean_sea_level_pressure":      ("prmsl", (1.0,    0.0)),
    "total_precipitation_6hr":      ("tp",    (1e-3,   0.0)),  # mm → m
    # GFS pgrb2.0p25 doesn't publish WTMP or SST directly — it ships
    # ``TMP:surface`` (skin temperature). cfgrib decodes that with
    # ecCodes shortName ``t`` (same paramId=130 as 2m temp) but with
    # typeOfLevel=surface, which makes it unambiguous alongside the
    # isobaric ``t`` messages. Over ocean cells, skin temperature ≈ SST;
    # over land cells, it's land-surface skin temperature (not NaN, unlike
    # ERA5's SST field). Gets GenCast past the missing-SST KeyError.
    "sea_surface_temperature":      ("t",     (1.0,    0.0)),
}


# ---------------------------------------------------------------------------
# Pressure-level variables (3D: time × level × lat × lon)
# ---------------------------------------------------------------------------
#
# GFS units on pressure levels:
#   t:   K       (matches ERA5)
#   q:   kg/kg   (matches ERA5)
#   u:   m/s     (matches ERA5)
#   v:   m/s     (matches ERA5)
#   w:   Pa/s    (matches ERA5 vertical_velocity)
#   gh:  gpm     (geopotential HEIGHT in meters — ERA5 has geopotential in m²/s²)
#                → multiply by g = 9.80665 to get geopotential.

PRESSURE_LEVEL_VARS: Dict[str, Tuple[str, Tuple[float, float]]] = {
    "temperature":              ("t",  (1.0,       0.0)),
    "specific_humidity":        ("q",  (1.0,       0.0)),
    "u_component_of_wind":      ("u",  (1.0,       0.0)),
    "v_component_of_wind":      ("v",  (1.0,       0.0)),
    "vertical_velocity":        ("w",  (1.0,       0.0)),
    "geopotential":             ("gh", (9.80665,   0.0)),  # gpm → m²/s²
}


# ---------------------------------------------------------------------------
# Static variables (no time dim)
# ---------------------------------------------------------------------------
#
# These aren't in standard GFS pgrb2 files. They're loaded from a small ERA5
# snapshot cached in the repo. See static_vars.py.

STATIC_VARS: Tuple[str, ...] = (
    "geopotential_at_surface",
    "land_sea_mask",
)


# ---------------------------------------------------------------------------
# Pressure levels
# ---------------------------------------------------------------------------
#
# GraphCast operational uses 13 levels. GenCast 1.0° uses the same 13 (the
# checkpoint's task_config lists them explicitly). Both models' task_configs
# carry the level list, so the fetcher never hard-codes it — but the levels
# here are what we select DOWN to from GFS's richer level set.
#
# GFS pgrb2.0p25 natively provides: 10, 20, 30, 40, 50, 70, 100, 150, 200,
# 250, 300, 350, 400, 450, 500, 550, 600, 650, 700, 750, 800, 850, 900, 925,
# 950, 975, 1000 hPa — all 13 GraphCast levels are in there.

GRAPHCAST_PRESSURE_LEVELS: Tuple[int, ...] = (
    50, 100, 150, 200, 250, 300, 400, 500, 600, 700, 850, 925, 1000,
)


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------

def gfs_short_name(era5_name: str) -> str:
    """Return the GFS short-name for an ERA5 variable, or raise KeyError."""
    if era5_name in SURFACE_VARS:
        return SURFACE_VARS[era5_name][0]
    if era5_name in PRESSURE_LEVEL_VARS:
        return PRESSURE_LEVEL_VARS[era5_name][0]
    raise KeyError(f"No GFS mapping for ERA5 variable {era5_name!r}")


def unit_convert(era5_name: str, gfs_values):
    """Apply the stored (scale, offset) conversion to a GFS value/array."""
    if era5_name in SURFACE_VARS:
        scale, offset = SURFACE_VARS[era5_name][1]
    elif era5_name in PRESSURE_LEVEL_VARS:
        scale, offset = PRESSURE_LEVEL_VARS[era5_name][1]
    else:
        raise KeyError(f"No unit conversion for {era5_name!r}")
    return gfs_values * scale + offset


def all_era5_names() -> Tuple[str, ...]:
    """All ERA5 canonical names handled by this mapping (surface + pressure)."""
    return tuple(SURFACE_VARS.keys()) + tuple(PRESSURE_LEVEL_VARS.keys())
