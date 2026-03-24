"""
DPI Agent — orchestrates multi-source profile assembly from Indian Digital Public Infrastructure.
Identifies farmers by phone, assembles composite profiles from 6 DPI services in parallel.
"""

from __future__ import annotations
import json
import logging
import uuid
from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from src.dpi.models import (
    AadhaarProfile, LandRecord, SoilHealthCard,
    PMKISANRecord, PMFBYRecord, KCCRecord, FarmerProfile,
)
from src.dpi.simulator import get_registry

log = logging.getLogger(__name__)

PROFILE_STALE_HOURS = 24


class DPIAgent:
    def __init__(self, simulation: bool = True):
        self.simulation = simulation

    async def identify_farmer(self, phone: str) -> Optional[AadhaarProfile]:
        from src.dpi.services import get_service
        svc = get_service("aadhaar", simulation=self.simulation)
        result = await svc.lookup(phone)
        if result is None:
            return None
        return AadhaarProfile(**result)

    async def assemble_profile(self, aadhaar_id: str) -> Optional[FarmerProfile]:
        """Look up composite FarmerProfile by Aadhaar ID."""
        registry = get_registry()
        return registry.lookup_by_aadhaar(aadhaar_id)

    async def get_or_create_profile(self, phone: str) -> Optional[FarmerProfile]:
        """Cache check -> identify -> assemble -> persist."""
        # Check DB cache first
        cached = self._load_cached_profile(phone)
        if cached is not None:
            return cached

        # Identify via eKYC
        aadhaar = await self.identify_farmer(phone)
        if aadhaar is None:
            return None

        # Assemble full profile
        profile = await self.assemble_profile(aadhaar.aadhaar_id)
        if profile is None:
            return None

        # Cache to DB
        self._cache_profile(profile)
        return profile

    def profile_to_context(self, profile: FarmerProfile) -> str:
        """Convert profile to structured text block for prompt injection."""
        lines = [
            f"FARMER PROFILE: {profile.aadhaar.name} ({profile.aadhaar.name_local})",
            f"  Location: {profile.aadhaar.district}, {profile.aadhaar.state}",
            f"  Language: {profile.aadhaar.language}",
            f"  Phone: {profile.aadhaar.phone}",
            "",
            f"LAND HOLDINGS ({profile.total_area:.2f} ha total):",
        ]
        for lr in profile.land_records:
            lines.append(
                f"  - Survey {lr.survey_number}: {lr.area_hectares:.2f} ha, "
                f"{lr.soil_type} soil, {lr.irrigation_type} irrigation"
            )
            lines.append(f"    Crops: {', '.join(lr.crops_registered)}")
            lines.append(f"    GPS: {lr.gps_lat}, {lr.gps_lon} (Station: {lr.nearest_station_id})")

        lines.append("")
        if profile.soil_health:
            sh = profile.soil_health
            lines.append(f"SOIL HEALTH CARD ({sh.card_number}):")
            lines.append(f"  pH: {sh.pH}, N/P/K: {sh.nitrogen_kg_ha:.0f}/{sh.phosphorus_kg_ha:.0f}/{sh.potassium_kg_ha:.0f} kg/ha")
            lines.append(f"  Organic Carbon: {sh.organic_carbon_pct}%, Classification: {sh.classification}")
            lines.append(f"  Recommendations: {'; '.join(sh.recommendations)}")

        lines.append("")
        if profile.pmkisan:
            pm = profile.pmkisan
            lines.append(f"PM-KISAN: {pm.holding_category} farmer, {pm.installments_received} installments received")

        if profile.pmfby:
            pf = profile.pmfby
            lines.append(f"CROP INSURANCE: {pf.status}, insured crops: {', '.join(pf.insured_crops)}")
            lines.append(f"  Sum insured: INR {pf.sum_insured:,.0f}, Premium: INR {pf.premium_paid:,.0f}")
            if pf.claim_history:
                lines.append(f"  Claims: {len(pf.claim_history)} filed")

        if profile.kcc:
            kc = profile.kcc
            util = (kc.outstanding / kc.credit_limit * 100) if kc.credit_limit > 0 else 0
            lines.append(f"KISAN CREDIT CARD: limit INR {kc.credit_limit:,.0f}, "
                        f"{util:.0f}% utilized, status: {kc.repayment_status}")

        return "\n".join(lines)

    def _load_cached_profile(self, phone: str) -> Optional[FarmerProfile]:
        try:
            from src.database import init_db
            conn = init_db()
            row = conn.execute(
                "SELECT profile_json, cached_at FROM farmer_profiles WHERE phone = ?",
                [phone],
            ).fetchone()
            if row is None:
                return None
            profile_json, cached_at = row
            if isinstance(cached_at, str):
                cached_dt = datetime.fromisoformat(cached_at)
            else:
                cached_dt = cached_at
            if datetime.utcnow() - cached_dt > timedelta(hours=PROFILE_STALE_HOURS):
                return None
            return _dict_to_profile(json.loads(profile_json))
        except Exception as exc:
            log.debug("Cache load failed: %s", exc)
            return None

    def _cache_profile(self, profile: FarmerProfile) -> None:
        try:
            from src.database import init_db
            conn = init_db()
            d = _profile_to_dict(profile)
            conn.execute(
                """INSERT INTO farmer_profiles
                   (id, aadhaar_id, phone, name, district, station_id,
                    primary_crops, total_area, profile_json, cached_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT (id) DO NOTHING""",
                [str(uuid.uuid4()), profile.aadhaar.aadhaar_id, profile.aadhaar.phone,
                 profile.aadhaar.name, profile.aadhaar.district,
                 profile.nearest_stations[0] if profile.nearest_stations else "",
                 json.dumps(profile.primary_crops),
                 profile.total_area,
                 json.dumps(d, default=str),
                 datetime.utcnow().isoformat()],
            )
        except Exception as exc:
            log.debug("Cache write failed: %s", exc)


def _profile_to_dict(p: FarmerProfile) -> dict:
    return asdict(p)


def _dict_to_profile(d: dict) -> FarmerProfile:
    aadhaar = AadhaarProfile(**d["aadhaar"])
    land = [LandRecord(**lr) for lr in d.get("land_records", [])]
    soil = SoilHealthCard(**d["soil_health"]) if d.get("soil_health") else None
    pmk = PMKISANRecord(**d["pmkisan"]) if d.get("pmkisan") else None
    pmf = PMFBYRecord(**d["pmfby"]) if d.get("pmfby") else None
    kcc = KCCRecord(**d["kcc"]) if d.get("kcc") else None
    return FarmerProfile(aadhaar=aadhaar, land_records=land, soil_health=soil,
                         pmkisan=pmk, pmfby=pmf, kcc=kcc)
