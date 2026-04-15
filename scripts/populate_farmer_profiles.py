#!/usr/bin/env python3
"""One-shot script to cache all DPI simulator farmers into the farmer_profiles table.

Run once: DATABASE_URL=... python3 scripts/populate_farmer_profiles.py

Idempotent: uses the farmer's phone number as the primary key so re-runs
overwrite the existing row instead of accumulating duplicates. The pipeline
itself still writes rows with random UUIDs via DPIAgent._cache_profile — those
coexist safely with this script's rows but are deduped elsewhere by phone.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict
from datetime import datetime, timezone

# Allow `python3 scripts/populate_farmer_profiles.py` from repo root.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.database import init_db  # noqa: E402
from src.database._util import get_database_url  # noqa: E402
from src.dpi.simulator import get_registry  # noqa: E402


def _profile_to_json(profile) -> str:
    return json.dumps(asdict(profile), default=str)


def main() -> int:
    db_url = get_database_url()
    conn = init_db(db_url)
    registry = get_registry()

    all_profiles = list(registry._farmers.values())
    if not all_profiles:
        print("No farmer profiles found in the DPI registry.")
        return 1

    now_iso = datetime.now(timezone.utc).isoformat()
    cached = 0

    for profile in all_profiles:
        aadhaar = profile.aadhaar
        station_id = profile.nearest_stations[0] if profile.nearest_stations else ""
        primary_crops_json = json.dumps(profile.primary_crops)
        profile_json = _profile_to_json(profile)

        # Use phone as the deterministic primary key so re-running this
        # script is idempotent. The DDL declares `id VARCHAR PRIMARY KEY`,
        # which matches the usual ON CONFLICT (id) shape.
        conn.execute(
            """INSERT INTO farmer_profiles
               (id, aadhaar_id, phone, name, district, station_id,
                primary_crops, total_area, profile_json, cached_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT (id) DO UPDATE SET
                   aadhaar_id    = EXCLUDED.aadhaar_id,
                   phone         = EXCLUDED.phone,
                   name          = EXCLUDED.name,
                   district      = EXCLUDED.district,
                   station_id    = EXCLUDED.station_id,
                   primary_crops = EXCLUDED.primary_crops,
                   total_area    = EXCLUDED.total_area,
                   profile_json  = EXCLUDED.profile_json,
                   cached_at     = EXCLUDED.cached_at""",
            [
                aadhaar.phone,           # id = phone (deterministic)
                aadhaar.aadhaar_id,
                aadhaar.phone,
                aadhaar.name,
                aadhaar.district,
                station_id,
                primary_crops_json,
                profile.total_area,
                profile_json,
                now_iso,
            ],
        )
        cached += 1

    print(f"Cached {cached} farmer profiles to farmer_profiles")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
