"""
Level 2A — DPI Profile Quality Evaluation

Measures coverage, completeness, geographic realism, and internal consistency
of the simulated DPI farmer registry.

Usage:
    python tests/eval_dpi.py
"""

import json
import os
from collections import defaultdict
from datetime import datetime

import pytest
from rich.console import Console
from rich.table import Table

from config import STATIONS, STATION_MAP

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "eval_results")

# Expected crops by station region for geographic realism checks
EXPECTED_CROPS = {
    "KL_TVM": {"coconut", "rubber", "banana", "tapioca", "pepper"},
    "KL_COK": {"coconut", "rubber", "pineapple", "nutmeg", "banana"},
    "KL_ALP": {"rice", "coconut", "banana", "tapioca"},
    "KL_KNR": {"coconut", "cashew", "pepper", "rubber", "arecanut"},
    "KL_KZD": {"coconut", "pepper", "arecanut", "rubber", "banana"},
    "KL_TCR": {"rice", "coconut", "arecanut"},
    "KL_KTM": {"rubber", "coconut", "pepper", "banana", "cardamom"},
    "KL_PKD": {"rice", "coconut", "groundnut", "arecanut", "banana"},
    "KL_PNL": {"rubber", "coconut", "cashew", "pepper", "tapioca"},
    "KL_NLB": {"coconut", "rubber", "arecanut", "pepper", "paddy"},
    "TN_TNJ": {"rice", "pulses", "sugarcane", "banana", "coconut"},
    "TN_MDU": {"paddy", "cotton", "groundnut", "millets", "banana"},
    "TN_TRZ": {"paddy", "banana", "sugarcane", "groundnut", "maize"},
    "TN_SLM": {"tapioca", "paddy", "groundnut", "maize", "turmeric"},
    "TN_ERD": {"turmeric", "sugarcane", "coconut", "cotton", "groundnut"},
    "TN_CHN": {"rice", "vegetables", "flowers"},
    "TN_TNV": {"paddy", "banana", "coconut", "cotton", "sugarcane"},
    "TN_CBE": {"coconut", "cotton", "sugarcane", "millets", "groundnut"},
    "TN_VLR": {"paddy", "groundnut", "sugarcane", "ragi", "mango"},
    "TN_NGP": {"rice", "pulses", "coconut", "banana"},
}

# Realistic pH ranges by soil type
PH_RANGES = {
    "laterite": (4.5, 6.5),
    "sandy loam": (5.0, 7.0),
    "alluvial": (5.5, 7.5),
    "sandy": (5.5, 7.5),
    "forest loam": (4.0, 6.0),
    "clay": (6.0, 8.0),
    "red": (5.5, 7.5),
    "black cotton": (7.0, 8.5),
    "black": (6.5, 8.0),
}


def run_dpi_eval():
    console = Console()
    console.print(f"\n[bold]Level 2A — DPI Profile Quality Eval[/bold]\n")

    from src.dpi.simulator import SimulatedDPIRegistry
    registry = SimulatedDPIRegistry()
    farmers = registry.list_farmers()

    console.print(f"Total farmers: {registry.farmer_count}")
    console.print(f"Total stations: {len(STATIONS)}\n")

    # ─── 1. Coverage ───────────────────────────────
    station_farmers = defaultdict(list)
    for f in farmers:
        station_farmers[f["station"]].append(f)

    all_station_ids = {s.station_id for s in STATIONS}
    covered = set(station_farmers.keys())
    missing = all_station_ids - covered
    coverage = len(covered) / len(all_station_ids) if all_station_ids else 0

    state_counts = defaultdict(int)
    for f in farmers:
        station = STATION_MAP.get(f["station"])
        if station:
            state_counts[station.state] += 1

    tbl_cov = Table(title="Station Coverage")
    tbl_cov.add_column("Metric", style="bold")
    tbl_cov.add_column("Value", justify="right")
    tbl_cov.add_row("Stations covered", f"{len(covered)}/{len(all_station_ids)}")
    tbl_cov.add_row("Coverage %", f"{coverage:.0%}")
    tbl_cov.add_row("Min farmers/station", str(min(len(v) for v in station_farmers.values())))
    tbl_cov.add_row("Max farmers/station", str(max(len(v) for v in station_farmers.values())))
    tbl_cov.add_row("Avg farmers/station", f"{len(farmers) / max(1, len(covered)):.1f}")
    for state, count in sorted(state_counts.items()):
        tbl_cov.add_row(f"  {state} farmers", str(count))
    if missing:
        tbl_cov.add_row("Missing stations", ", ".join(sorted(missing)))
    console.print(tbl_cov)

    # ─── 2. Completeness ──────────────────────────
    complete_count = 0
    partial_counts = defaultdict(int)
    for f in farmers:
        profile = registry.lookup_by_phone(f["phone"])
        has = {
            "aadhaar": profile.aadhaar is not None,
            "land_records": len(profile.land_records) > 0,
            "soil_health": profile.soil_health is not None,
            "pmkisan": profile.pmkisan is not None,
            "pmfby": profile.pmfby is not None,
            "kcc": profile.kcc is not None,
        }
        if all(has.values()):
            complete_count += 1
        for source, present in has.items():
            if present:
                partial_counts[source] += 1

    completeness = complete_count / len(farmers) if farmers else 0

    tbl_comp = Table(title="\nProfile Completeness")
    tbl_comp.add_column("DPI Source", style="bold")
    tbl_comp.add_column("Populated", justify="right")
    tbl_comp.add_column("Rate", justify="right")
    for source in ["aadhaar", "land_records", "soil_health", "pmkisan", "pmfby", "kcc"]:
        count = partial_counts[source]
        rate = count / len(farmers) if farmers else 0
        tbl_comp.add_row(source, f"{count}/{len(farmers)}", f"{rate:.0%}")
    tbl_comp.add_row("All 6 sources", f"{complete_count}/{len(farmers)}", f"{completeness:.0%}")
    console.print(tbl_comp)

    # ─── 3. Geographic Realism ─────────────────────
    crop_matches = 0
    crop_total = 0
    crop_mismatches = []
    for f in farmers:
        sid = f["station"]
        expected = EXPECTED_CROPS.get(sid, set())
        actual = set(f["crops"])
        crop_total += 1
        if actual.issubset(expected):
            crop_matches += 1
        else:
            unexpected = actual - expected
            if unexpected:
                crop_mismatches.append((f["name"], sid, unexpected))

    crop_realism = crop_matches / crop_total if crop_total else 0

    # pH vs soil type check
    ph_matches = 0
    ph_total = 0
    ph_mismatches = []
    for f in farmers:
        profile = registry.lookup_by_phone(f["phone"])
        if profile.soil_health and profile.land_records:
            soil_type = profile.land_records[0].soil_type
            pH = profile.soil_health.pH
            expected_range = PH_RANGES.get(soil_type)
            ph_total += 1
            if expected_range and expected_range[0] <= pH <= expected_range[1]:
                ph_matches += 1
            elif expected_range:
                ph_mismatches.append((f["name"], soil_type, pH, expected_range))

    ph_realism = ph_matches / ph_total if ph_total else 0

    # Holding size check
    area_by_state = defaultdict(list)
    for f in farmers:
        station = STATION_MAP.get(f["station"])
        if station:
            area_by_state[station.state].append(f["area_ha"])

    tbl_real = Table(title="\nGeographic Realism")
    tbl_real.add_column("Check", style="bold")
    tbl_real.add_column("Pass", justify="right")
    tbl_real.add_column("Total", justify="right")
    tbl_real.add_column("Rate", justify="right")
    tbl_real.add_row("Crops match station region", str(crop_matches), str(crop_total), f"{crop_realism:.0%}")
    tbl_real.add_row("Soil pH in expected range", str(ph_matches), str(ph_total), f"{ph_realism:.0%}")
    console.print(tbl_real)

    if crop_mismatches:
        console.print(f"\n[yellow]Crop mismatches ({len(crop_mismatches)}):[/yellow]")
        for name, sid, unexpected in crop_mismatches[:5]:
            console.print(f"  {name} ({sid}): unexpected crops {unexpected}")

    # Holding size by state
    tbl_area = Table(title="\nHolding Size by State")
    tbl_area.add_column("State", style="bold")
    tbl_area.add_column("Count", justify="right")
    tbl_area.add_column("Min (ha)", justify="right")
    tbl_area.add_column("Avg (ha)", justify="right")
    tbl_area.add_column("Max (ha)", justify="right")
    for state in sorted(area_by_state):
        areas = area_by_state[state]
        tbl_area.add_row(state, str(len(areas)),
                          f"{min(areas):.2f}", f"{sum(areas)/len(areas):.2f}",
                          f"{max(areas):.2f}")
    console.print(tbl_area)

    # ─── 4. Internal Consistency ───────────────────
    consistency_checks = 0
    consistency_pass = 0
    consistency_issues = []

    for f in farmers:
        profile = registry.lookup_by_phone(f["phone"])

        # Check: holding category matches area
        if profile.pmkisan and profile.land_records:
            area = profile.total_area
            cat = profile.pmkisan.holding_category
            consistency_checks += 1
            expected_cat = "marginal" if area < 1.0 else ("small" if area < 2.0 else "semi-medium")
            if cat == expected_cat:
                consistency_pass += 1
            else:
                consistency_issues.append(
                    f"{f['name']}: area={area:.2f}ha, category={cat} (expected {expected_cat})"
                )

        # Check: KCC crops match land record crops
        if profile.kcc and profile.land_records:
            kcc_crops = set(profile.kcc.crops_financed)
            land_crops = set(profile.primary_crops)
            consistency_checks += 1
            if kcc_crops.issubset(land_crops):
                consistency_pass += 1
            else:
                diff = kcc_crops - land_crops
                if diff:
                    consistency_issues.append(
                        f"{f['name']}: KCC crops {diff} not in land records"
                    )

        # Check: GPS near station
        if profile.land_records:
            lr = profile.land_records[0]
            station = STATION_MAP.get(lr.nearest_station_id)
            if station:
                lat_diff = abs(lr.gps_lat - station.lat)
                lon_diff = abs(lr.gps_lon - station.lon)
                consistency_checks += 1
                if lat_diff < 0.1 and lon_diff < 0.1:
                    consistency_pass += 1
                else:
                    consistency_issues.append(
                        f"{f['name']}: GPS ({lr.gps_lat:.4f},{lr.gps_lon:.4f}) "
                        f"far from station ({station.lat:.4f},{station.lon:.4f})"
                    )

    consistency_rate = consistency_pass / consistency_checks if consistency_checks else 0

    tbl_con = Table(title="\nInternal Consistency")
    tbl_con.add_column("Check", style="bold")
    tbl_con.add_column("Result", justify="right")
    tbl_con.add_row("Total checks", str(consistency_checks))
    tbl_con.add_row("Passed", str(consistency_pass))
    tbl_con.add_row("Consistency rate", f"{consistency_rate:.0%}")
    if consistency_issues:
        tbl_con.add_row("Issues", str(len(consistency_issues)))
    console.print(tbl_con)

    if consistency_issues:
        console.print(f"\n[yellow]Consistency issues ({len(consistency_issues)}):[/yellow]")
        for issue in consistency_issues[:5]:
            console.print(f"  {issue}")

    # ─── 5. Profile-to-Context Quality ─────────────
    from src.dpi import DPIAgent
    agent = DPIAgent()
    context_lengths = []
    context_sections = defaultdict(int)
    for f in farmers[:10]:
        profile = registry.lookup_by_phone(f["phone"])
        ctx = agent.profile_to_context(profile)
        context_lengths.append(len(ctx))
        for section in ["FARMER PROFILE", "LAND HOLDINGS", "SOIL HEALTH CARD",
                        "PM-KISAN", "CROP INSURANCE", "KISAN CREDIT CARD"]:
            if section in ctx:
                context_sections[section] += 1

    tbl_ctx = Table(title="\nContext Block Quality (sample of 10)")
    tbl_ctx.add_column("Section", style="bold")
    tbl_ctx.add_column("Present", justify="right")
    for section in ["FARMER PROFILE", "LAND HOLDINGS", "SOIL HEALTH CARD",
                    "PM-KISAN", "CROP INSURANCE", "KISAN CREDIT CARD"]:
        tbl_ctx.add_row(section, f"{context_sections[section]}/10")
    tbl_ctx.add_row("Avg context length", f"{sum(context_lengths)/len(context_lengths):.0f} chars")
    console.print(tbl_ctx)

    # ─── Save ──────────────────────────────────────
    os.makedirs(RESULTS_DIR, exist_ok=True)
    results = {
        "eval_name": "dpi",
        "timestamp": datetime.utcnow().isoformat(),
        "total_farmers": registry.farmer_count,
        "coverage": {
            "stations_covered": len(covered),
            "stations_total": len(all_station_ids),
            "coverage_rate": coverage,
            "min_per_station": min(len(v) for v in station_farmers.values()),
            "max_per_station": max(len(v) for v in station_farmers.values()),
            "by_state": dict(state_counts),
        },
        "completeness": {
            "fully_complete": complete_count,
            "completeness_rate": completeness,
            "by_source": {s: partial_counts[s] for s in
                          ["aadhaar", "land_records", "soil_health", "pmkisan", "pmfby", "kcc"]},
        },
        "geographic_realism": {
            "crop_match_rate": crop_realism,
            "ph_match_rate": ph_realism,
            "crop_mismatches": len(crop_mismatches),
            "ph_mismatches": len(ph_mismatches),
            "avg_area_by_state": {s: sum(a)/len(a) for s, a in area_by_state.items()},
        },
        "consistency": {
            "checks": consistency_checks,
            "passed": consistency_pass,
            "rate": consistency_rate,
            "issues": len(consistency_issues),
        },
        "context_quality": {
            "avg_length_chars": sum(context_lengths) / len(context_lengths) if context_lengths else 0,
            "sections_present": dict(context_sections),
        },
    }
    out = os.path.join(RESULTS_DIR, "dpi.json")
    with open(out, "w") as f:
        json.dump(results, f, indent=2, default=str)
    console.print(f"\n[dim]Results saved to {out}[/dim]")
    return results


@pytest.mark.slow
@pytest.mark.offline
def test_eval_dpi():
    """Pytest wrapper for standalone eval script."""
    results = run_dpi_eval()
    assert results is not None


if __name__ == "__main__":
    run_dpi_eval()
