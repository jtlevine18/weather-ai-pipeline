#!/usr/bin/env python3
"""
Phase 0 batch driver — runs gencast_load_test.py three times in sequence
with different memory-optimization knobs, each in a fresh Python subprocess
so JAX state is clean between configs.

Variants tested (all 0.25°):
  A  mask_type="lazy"          — lighter attention masks
  B  num_noise_levels=8        — fewer diffusion denoising steps
  C  checkpoint="0p25deg <2019" — older/possibly smaller 0.25° checkpoint

Each variant writes to /tmp/gencast_load.log with a [LABEL] prefix. All
results collated in /tmp/gencast_batch_summary.log.

Usage:
    python scripts/gencast_load_batch.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

LOG_PATH = Path("/tmp/gencast_load.log")
SUMMARY = Path("/tmp/gencast_batch_summary.log")
SCRIPT = Path(__file__).parent / "gencast_load_test.py"

VARIANTS = [
    # Singles on 0.25° Operational
    {
        "GENCAST_LABEL": "A_lazy",
        "GENCAST_CHECKPOINT_MATCH": "Operational",
        "GENCAST_MASK_TYPE": "lazy",
    },
    {
        "GENCAST_LABEL": "B_noise8",
        "GENCAST_CHECKPOINT_MATCH": "Operational",
        "GENCAST_MASK_TYPE": "full",
        "GENCAST_NOISE_LEVELS": "8",
    },
    # Operational + both knobs (A+B)
    {
        "GENCAST_LABEL": "AB_lazy_noise8",
        "GENCAST_CHECKPOINT_MATCH": "Operational",
        "GENCAST_MASK_TYPE": "lazy",
        "GENCAST_NOISE_LEVELS": "8",
    },
    # Older 0.25° checkpoint alone (C)
    {
        "GENCAST_LABEL": "C_older",
        "GENCAST_CHECKPOINT_MATCH": "0p25deg <2019",
        "GENCAST_MASK_TYPE": "full",
    },
    # Kitchen sink: older checkpoint + both knobs (A+B+C)
    {
        "GENCAST_LABEL": "ABC_kitchen_sink",
        "GENCAST_CHECKPOINT_MATCH": "0p25deg <2019",
        "GENCAST_MASK_TYPE": "lazy",
        "GENCAST_NOISE_LEVELS": "8",
    },
]


def main() -> int:
    # Fresh log at start of batch
    if LOG_PATH.exists():
        LOG_PATH.unlink()
    SUMMARY.write_text("# GenCast Phase 0 batch summary\n")

    results = []
    for i, variant in enumerate(VARIANTS, 1):
        label = variant["GENCAST_LABEL"]
        print(f"\n{'#' * 60}\n[batch {i}/{len(VARIANTS)}] variant {label}\n{'#' * 60}", flush=True)

        env = {**os.environ, **variant, "GENCAST_APPEND_LOG": "1"}
        t0 = time.time()
        rc = subprocess.run(
            [sys.executable, str(SCRIPT)],
            env=env,
            check=False,
        ).returncode
        elapsed = time.time() - t0

        result = {
            "label": label,
            "returncode": rc,
            "elapsed_s": round(elapsed, 1),
            "variant": variant,
        }
        results.append(result)
        with SUMMARY.open("a") as f:
            f.write(f"\n[{label}] rc={rc} elapsed={elapsed:.1f}s variant={variant}\n")
        print(f"[batch {i}/{len(VARIANTS)}] {label} rc={rc} in {elapsed:.1f}s", flush=True)

    print("\n" + "#" * 60, flush=True)
    print("BATCH SUMMARY", flush=True)
    for r in results:
        status = "PASS" if r["returncode"] == 0 else f"FAIL(rc={r['returncode']})"
        print(f"  {r['label']:24s} {status:12s} {r['elapsed_s']:7.1f}s", flush=True)
    print("#" * 60, flush=True)

    # Non-zero only if ALL variants failed
    return 0 if any(r["returncode"] == 0 for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
