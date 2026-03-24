#!/usr/bin/env python3
"""Full end-to-end NeuralGCM diagnostic — ERA5 fetch through station extraction."""

import time as time_mod
import numpy as np


def check_nan(ds, label):
    print(f"\n  [{label}]")
    for var in ds.data_vars:
        arr = ds[var]
        total = int(arr.size)
        nan_count = int(arr.isnull().sum().values)
        status = "OK" if nan_count == 0 else f"NaN={nan_count}/{total} ({nan_count/total*100:.1f}%)"
        print(f"    {var:35s} {status}")


def main():
    print("=" * 60)
    print("  NeuralGCM FULL end-to-end test (CPU)")
    print("=" * 60)

    # ---- Step 1: Load model ----
    print("\n[1/9] Loading NeuralGCM checkpoint...")
    t0 = time_mod.time()
    import neuralgcm, gcsfs, pickle
    gcs = gcsfs.GCSFileSystem(token="anon")
    with gcs.open("gs://neuralgcm/models/v1/deterministic_1_4_deg.pkl", "rb") as f:
        model = neuralgcm.PressureLevelModel.from_checkpoint(pickle.load(f))
    print(f"    Loaded in {time_mod.time()-t0:.1f}s")

    # ---- Step 2: Fetch ERA5 ----
    print("\n[2/9] Fetching ERA5 initial conditions...")
    import xarray as xr
    ERA5_PATH = "gs://gcp-public-data-arco-era5/ar/full_37-1h-0p25deg-chunk-1.zarr-v3"
    full_ds = xr.open_zarr(ERA5_PATH, chunks=None,
                           storage_options={"token": "anon"}, consolidated=True)

    all_vars = model.input_variables + model.forcing_variables
    available = [v for v in all_vars if v in full_ds]
    now = np.datetime64("now")
    test_var = available[0]
    init_time = None

    for lag_days in range(5, 12):
        candidate = now - np.timedelta64(lag_days * 24, "h")
        candidate = full_ds.time.sel(time=candidate, method="nearest").values
        probe = full_ds[test_var].sel(time=candidate).isel(level=0, latitude=360, longitude=720)
        val = float(probe.compute().values)
        if not np.isnan(val):
            init_time = candidate
            print(f"    Found data at lag={lag_days}d: {init_time}")
            break

    if init_time is None:
        print("    ERROR: No data found!")
        return

    t0 = time_mod.time()
    data = full_ds[available].sel(time=slice(init_time, init_time)).compute()
    print(f"    Fetched {len(available)} vars in {time_mod.time()-t0:.1f}s")

    # ---- Step 3: Fill forcing NaN ----
    print("\n[3/9] Filling forcing NaN...")
    for var in model.forcing_variables:
        if var in data and data[var].isnull().any():
            mean_val = float(data[var].mean(skipna=True).values)
            data[var] = data[var].fillna(mean_val if not np.isnan(mean_val) else 0.0)
            print(f"    Filled {var} with mean={mean_val:.2f}")

    # ---- Step 4: Regrid ----
    print("\n[4/9] Regridding ERA5 → model grid...")
    from dinosaur import spherical_harmonic, horizontal_interpolation, xarray_utils

    era5_grid = spherical_harmonic.Grid(
        latitude_nodes=data.sizes["latitude"],
        longitude_nodes=data.sizes["longitude"],
        latitude_spacing=xarray_utils.infer_latitude_spacing(data.latitude),
        longitude_offset=xarray_utils.infer_longitude_offset(data.longitude),
    )
    regridder = horizontal_interpolation.ConservativeRegridder(
        era5_grid, model.data_coords.horizontal, skipna=True,
    )
    t0 = time_mod.time()
    regridded = xarray_utils.regrid(data, regridder)
    regridded = xarray_utils.fill_nan_with_nearest(regridded)
    print(f"    Regridded in {time_mod.time()-t0:.1f}s")
    check_nan(regridded, "Post-regrid")

    # ---- Step 5: inputs_from_xarray ----
    print("\n[5/9] model.inputs_from_xarray...")
    t0 = time_mod.time()
    inputs = model.inputs_from_xarray(regridded.isel(time=0))
    print(f"    OK in {time_mod.time()-t0:.1f}s — type={type(inputs).__name__}")

    # ---- Step 6: forcings_from_xarray ----
    print("\n[6/9] model.forcings_from_xarray...")
    t0 = time_mod.time()
    forcings = model.forcings_from_xarray(regridded.isel(time=0))
    print(f"    OK in {time_mod.time()-t0:.1f}s — type={type(forcings).__name__}")

    # ---- Step 7: encode ----
    print("\n[7/9] model.encode (initial state)...")
    import jax
    t0 = time_mod.time()
    rng_key = jax.random.key(42)
    initial_state = model.encode(inputs, forcings, rng_key)
    print(f"    OK in {time_mod.time()-t0:.1f}s")

    # ---- Step 8: unroll (SHORT — just 2 steps to prove it works) ----
    # On CPU, full 168h would take very long. Do 2 × 6h = 12h to validate.
    all_forcings = model.forcings_from_xarray(regridded.head(time=1))
    inner_steps = 6
    test_outer_steps = 2  # 12h forecast — just to prove unroll works on CPU
    timedelta = np.timedelta64(inner_steps, "h")

    print(f"\n[8/9] model.unroll ({test_outer_steps} steps × {inner_steps}h = {test_outer_steps*inner_steps}h)...")
    print("    (Short test — full forecast would be ~168h on GPU)")
    t0 = time_mod.time()
    final_state, predictions = model.unroll(
        initial_state,
        all_forcings,
        steps=test_outer_steps,
        timedelta=timedelta,
        start_with_input=True,
    )
    unroll_s = time_mod.time() - t0
    print(f"    OK in {unroll_s:.1f}s")

    # ---- Step 9: data_to_xarray + station extraction ----
    print("\n[9/9] data_to_xarray + station extraction...")
    times = [
        init_time + np.timedelta64(i * inner_steps, "h")
        for i in range(test_outer_steps + 1)
    ]
    t0 = time_mod.time()
    output_ds = model.data_to_xarray(predictions, times=times)
    print(f"    data_to_xarray OK in {time_mod.time()-t0:.1f}s")
    print(f"    Output dims: {dict(output_ds.sizes)}")
    print(f"    Output vars: {list(output_ds.data_vars)}")
    print(f"    Time range: {output_ds.time[0].values} → {output_ds.time[-1].values}")
    check_nan(output_ds, "Model output")

    # Test station extraction with a few stations
    from config import STATIONS
    test_stations = STATIONS[:3]
    print(f"\n    Extracting forecasts for {len(test_stations)} test stations...")

    # Reuse the extraction logic from neuralgcm_client
    from src.neuralgcm_client import NeuralGCMClient
    client = NeuralGCMClient.__new__(NeuralGCMClient)
    client._model = model
    forecasts = client._extract_station_forecasts(output_ds, test_stations)

    for sid, fc_list in forecasts.items():
        print(f"\n    Station {sid}: {len(fc_list)} timesteps")
        for fc in fc_list[:2]:
            print(f"      {fc['ts']}: temp={fc['temperature']}°C, "
                  f"humidity={fc['humidity']}%, wind={fc['wind_speed']}km/h, "
                  f"pressure={fc['pressure']}hPa, rain={fc['rainfall']}mm")

    print("\n" + "=" * 60)
    print("  ALL 9 STEPS PASSED — NeuralGCM pipeline is working!")
    print("=" * 60)
    print(f"\n  On GPU (HF Spaces L4), expect:")
    print(f"    ERA5 fetch:  ~25s")
    print(f"    Regrid:      ~5s")
    print(f"    Encode:      ~10s (first JIT compile)")
    print(f"    Unroll 28×6h: ~30-60s")
    print(f"    Total:       ~2 min")


if __name__ == "__main__":
    main()
