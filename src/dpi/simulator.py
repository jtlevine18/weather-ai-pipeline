"""
Simulated farmer registry — demo users tied to weather stations.

Generates 30-50 realistic farmer profiles for pipeline demos.
Deterministic: seed = hash(station_id + index) for reproducibility.
Phone number is primary key (matches real-world identification flow).

The default templates are for Kerala & Tamil Nadu (India). To adapt for
another region, create a farmers.json file in the project root with the
same structure as STATION_FARMER_TEMPLATES below. The simulator will
load it automatically and generate demo farmers for your stations.

farmers.json format::

    {
      "MY_STATION_1": {
        "district": "District Name", "state": "State/Province", "lang": "en",
        "crops": ["crop1", "crop2"], "soil": ["clay", "loam"],
        "irrigation": ["canal", "rainfed"], "area": [0.5, 3.0], "pH": [5.5, 7.0],
        "names": [["Full Name", "নাম"], ["Another Name", "নাম"]],
        "count": 2
      }
    }
"""

from __future__ import annotations
import hashlib
import json
import os
import random
from typing import Any, Dict, List, Optional

from src.dpi.models import (
    AadhaarProfile, LandRecord, SoilHealthCard,
    PMKISANRecord, PMFBYRecord, KCCRecord, FarmerProfile,
)


# ---------------------------------------------------------------------------
# Station-specific farmer templates — loaded from farmers.json or hardcoded
# ---------------------------------------------------------------------------

_FARMERS_JSON = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "farmers.json"
)

# Pilot-scale override: how many farmers to generate per station at import time.
# 20 stations * 100 = 2,000 farmers — a realistic year-1 cooperative / block
# extension rollout for Kerala + Tamil Nadu. Deterministic generation is
# unchanged (still seeded by station_id + index), so the same 2,000 farmers
# appear on every restart. Set PILOT_FARMERS_PER_STATION=2 to fall back to
# the demo-sized registry.
_PILOT_FARMERS_PER_STATION = int(os.environ.get("PILOT_FARMERS_PER_STATION", "100"))

_HARDCODED_TEMPLATES: Dict[str, Dict[str, Any]] = {
    # Kerala — coastal
    "KL_TVM": dict(district="Thiruvananthapuram", state="Kerala", lang="ml",
                   crops=["coconut", "rubber", "banana", "tapioca", "pepper"], soil=["laterite", "sandy loam"],
                   irrigation=["rainfed", "well"], area=(0.2, 1.2), pH=(5.0, 6.2), count=2),
    "KL_COK": dict(district="Ernakulam", state="Kerala", lang="ml",
                   crops=["coconut", "rubber", "pineapple", "nutmeg", "banana"], soil=["laterite", "alluvial"],
                   irrigation=["well", "rainfed"], area=(0.3, 1.5), pH=(5.2, 6.5), count=2),
    "KL_ALP": dict(district="Alappuzha", state="Kerala", lang="ml",
                   crops=["rice", "coconut", "banana", "tapioca"], soil=["alluvial", "sandy"],
                   irrigation=["canal", "rainfed"], area=(0.3, 1.0), pH=(5.5, 6.5), count=2),
    "KL_KNR": dict(district="Kannur", state="Kerala", lang="ml",
                   crops=["coconut", "cashew", "pepper", "rubber", "arecanut"], soil=["laterite"],
                   irrigation=["well", "rainfed"], area=(0.3, 1.2), pH=(5.0, 6.3), count=2),
    "KL_KZD": dict(district="Kozhikode", state="Kerala", lang="ml",
                   crops=["coconut", "pepper", "arecanut", "rubber", "banana"], soil=["laterite", "sandy loam"],
                   irrigation=["well", "rainfed"], area=(0.2, 1.3), pH=(5.0, 6.2), count=2),
    # Kerala — midland
    "KL_TCR": dict(district="Thrissur", state="Kerala", lang="ml",
                   crops=["rice", "coconut", "arecanut"], soil=["alluvial", "laterite"],
                   irrigation=["canal", "well"], area=(0.4, 1.8), pH=(5.5, 6.5), count=2),
    "KL_KTM": dict(district="Kottayam", state="Kerala", lang="ml",
                   crops=["rubber", "coconut", "pepper", "banana", "cardamom"], soil=["laterite", "alluvial"],
                   irrigation=["well", "canal"], area=(0.4, 1.5), pH=(5.3, 6.3), count=2),
    "KL_PKD": dict(district="Palakkad", state="Kerala", lang="ml",
                   crops=["rice", "coconut", "groundnut", "arecanut", "banana"], soil=["alluvial", "red"],
                   irrigation=["canal", "borewell"], area=(0.5, 2.5), pH=(5.8, 7.0), count=2),
    # Kerala — Kollam district (Punalur replaces Kollam city)
    "KL_PNL": dict(district="Kollam", state="Kerala", lang="ml",
                   crops=["rubber", "coconut", "cashew", "pepper", "tapioca"], soil=["laterite"],
                   irrigation=["rainfed", "well"], area=(0.2, 1.0), pH=(5.0, 6.0), count=2),
    # Kerala — foothills (Nilambur replaces Wayanad)
    "KL_NLB": dict(district="Malappuram", state="Kerala", lang="ml",
                   crops=["coconut", "rubber", "arecanut", "pepper", "paddy"], soil=["laterite", "alluvial"],
                   irrigation=["well", "rainfed"], area=(0.3, 1.2), pH=(5.0, 6.2), count=2),
    # Tamil Nadu — delta
    "TN_TNJ": dict(district="Thanjavur", state="Tamil Nadu", lang="ta",
                   crops=["rice", "pulses", "sugarcane", "banana", "coconut"], soil=["alluvial", "clay"],
                   irrigation=["canal"], area=(0.8, 3.0), pH=(6.5, 7.5), count=3),
    # Tamil Nadu — dry zone
    "TN_MDU": dict(district="Madurai", state="Tamil Nadu", lang="ta",
                   crops=["paddy", "cotton", "groundnut", "millets", "banana"], soil=["red", "black cotton"],
                   irrigation=["borewell", "rainfed"], area=(1.0, 4.0), pH=(7.0, 8.0), count=2),
    "TN_TRZ": dict(district="Tiruchirappalli", state="Tamil Nadu", lang="ta",
                   crops=["paddy", "banana", "sugarcane", "groundnut", "maize"], soil=["red", "black cotton"],
                   irrigation=["borewell", "canal"], area=(1.0, 3.5), pH=(7.0, 7.8), count=2),
    "TN_SLM": dict(district="Salem", state="Tamil Nadu", lang="ta",
                   crops=["tapioca", "paddy", "groundnut", "maize", "turmeric"], soil=["red", "black cotton"],
                   irrigation=["borewell", "well"], area=(1.0, 4.0), pH=(7.0, 7.8), count=2),
    "TN_ERD": dict(district="Erode", state="Tamil Nadu", lang="ta",
                   crops=["turmeric", "sugarcane", "coconut", "cotton", "groundnut"], soil=["red", "black cotton"],
                   irrigation=["canal", "borewell"], area=(1.0, 3.5), pH=(6.8, 7.5), count=2),
    # Tamil Nadu — coastal
    "TN_CHN": dict(district="Chennai", state="Tamil Nadu", lang="ta",
                   crops=["rice", "vegetables", "flowers"], soil=["alluvial", "sandy"],
                   irrigation=["tank", "borewell"], area=(0.5, 2.0), pH=(6.5, 7.5), count=2),
    "TN_TNV": dict(district="Tirunelveli", state="Tamil Nadu", lang="ta",
                   crops=["paddy", "banana", "coconut", "cotton", "sugarcane"], soil=["alluvial", "red"],
                   irrigation=["tank", "canal"], area=(0.5, 2.5), pH=(6.5, 7.3), count=2),
    # Tamil Nadu — western
    "TN_CBE": dict(district="Coimbatore", state="Tamil Nadu", lang="ta",
                   crops=["coconut", "cotton", "sugarcane", "millets", "groundnut"], soil=["red", "black"],
                   irrigation=["well", "canal"], area=(0.5, 2.5), pH=(6.0, 7.0), count=2),
    "TN_VLR": dict(district="Vellore", state="Tamil Nadu", lang="ta",
                   crops=["paddy", "groundnut", "sugarcane", "ragi", "mango"], soil=["red", "black"],
                   irrigation=["well", "borewell"], area=(0.5, 2.0), pH=(6.0, 6.8), count=2),
    # Tamil Nadu — Bay of Bengal coast (Nagappattinam replaces Dindigul)
    "TN_NGP": dict(district="Nagappattinam", state="Tamil Nadu", lang="ta",
                   crops=["rice", "pulses", "coconut", "banana"], soil=["alluvial", "sandy"],
                   irrigation=["canal", "tank"], area=(0.5, 2.5), pH=(6.5, 7.5), count=2),
}

# Malayalam and Tamil name pools
_ML_NAMES = [
    ("Arun Kumar", "\u0d05\u0d30\u0d41\u0d7a \u0d15\u0d41\u0d2e\u0d3e\u0d7c"),
    ("Biju Thomas", "\u0d2c\u0d3f\u0d1c\u0d41 \u0d24\u0d4b\u0d2e\u0d38\u0d4d"),
    ("Suresh Nair", "\u0d38\u0d41\u0d30\u0d47\u0d36\u0d4d \u0d28\u0d3e\u0d2f\u0d7c"),
    ("Rajesh Menon", "\u0d30\u0d3e\u0d1c\u0d47\u0d36\u0d4d \u0d2e\u0d47\u0d28\u0d4b\u0d7b"),
    ("Priya Devi", "\u0d2a\u0d4d\u0d30\u0d3f\u0d2f \u0d26\u0d47\u0d35\u0d3f"),
    ("Meena K", "\u0d2e\u0d40\u0d28 \u0d15\u0d46"),
    ("Gopal Krishnan", "\u0d17\u0d4b\u0d2a\u0d3e\u0d32\u0d4d\u200d \u0d15\u0d43\u0d37\u0d4d\u0d23\u0d7b"),
    ("Lakshmi S", "\u0d32\u0d15\u0d4d\u0d37\u0d4d\u0d2e\u0d3f \u0d0e\u0d38\u0d4d"),
    ("Vijayan P", "\u0d35\u0d3f\u0d1c\u0d2f\u0d7b \u0d2a\u0d3f"),
    ("Anitha R", "\u0d05\u0d28\u0d3f\u0d24 \u0d06\u0d7c"),
    ("Mohan Das", "\u0d2e\u0d4b\u0d39\u0d7b \u0d26\u0d3e\u0d38\u0d4d"),
    ("Sathi K", "\u0d38\u0d24\u0d3f \u0d15\u0d46"),
    ("Rajan V", "\u0d30\u0d3e\u0d1c\u0d7b \u0d35\u0d3f"),
    ("Deepa M", "\u0d26\u0d40\u0d2a \u0d0e\u0d02"),
    ("Jayakumar", "\u0d1c\u0d2f\u0d15\u0d41\u0d2e\u0d3e\u0d7c"),
]

_TA_NAMES = [
    ("Murugan P", "\u0bae\u0bc1\u0bb0\u0bc1\u0b95\u0ba9\u0bcd \u0baa\u0bbf"),
    ("Selvi R", "\u0b9a\u0bc6\u0bb2\u0bcd\u0bb5\u0bbf \u0b86\u0bb0\u0bcd"),
    ("Ravi S", "\u0bb0\u0bb5\u0bbf \u0b8e\u0b9a\u0bcd"),
    ("Lakshmi N", "\u0bb2\u0b9f\u0bcd\u0b9a\u0bc1\u0bae\u0bbf \u0b8e\u0ba9\u0bcd"),
    ("Senthil Kumar", "\u0b9a\u0bc6\u0ba8\u0bcd\u0ba4\u0bbf\u0bb2\u0bcd \u0b95\u0bc1\u0bae\u0bbe\u0bb0\u0bcd"),
    ("Kavitha M", "\u0b95\u0bb5\u0bbf\u0ba4\u0bbe \u0b8e\u0bae\u0bcd"),
    ("Palani V", "\u0baa\u0bb4\u0ba9\u0bbf \u0bb5\u0bbf"),
    ("Meena S", "\u0bae\u0bc0\u0ba9\u0bbe \u0b8e\u0b9a\u0bcd"),
    ("Karthik R", "\u0b95\u0bbe\u0bb0\u0bcd\u0ba4\u0bcd\u0ba4\u0bbf\u0b95\u0bcd \u0b86\u0bb0\u0bcd"),
    ("Devi P", "\u0ba4\u0bc7\u0bb5\u0bbf \u0baa\u0bbf"),
    ("Anbu M", "\u0b85\u0ba9\u0bcd\u0baa\u0bc1 \u0b8e\u0bae\u0bcd"),
    ("Velu K", "\u0bb5\u0bc7\u0bb2\u0bc1 \u0b95\u0bc6"),
    ("Thangam S", "\u0ba4\u0b99\u0bcd\u0b95\u0bae\u0bcd \u0b8e\u0b9a\u0bcd"),
    ("Gopi N", "\u0b95\u0bcb\u0baa\u0bbf \u0b8e\u0ba9\u0bcd"),
    ("Saroja V", "\u0b9a\u0bb0\u0bcb\u0b9c\u0bbe \u0bb5\u0bbf"),
]


def _load_farmer_templates() -> Dict[str, Dict[str, Any]]:
    """Load farmer templates from farmers.json if it exists, else use hardcoded.

    Applies the PILOT_FARMERS_PER_STATION scale-up override to every template,
    so a weekly pipeline run works with a realistic pilot population without
    touching the template definitions themselves.
    """
    if os.path.exists(_FARMERS_JSON):
        try:
            with open(_FARMERS_JSON) as f:
                data = json.load(f)
            # Convert JSON lists to tuples where needed (area, pH ranges)
            for sid, tpl in data.items():
                if isinstance(tpl.get("area"), list):
                    tpl["area"] = tuple(tpl["area"])
                if isinstance(tpl.get("pH"), list):
                    tpl["pH"] = tuple(tpl["pH"])
            templates = data
        except Exception:
            templates = dict(_HARDCODED_TEMPLATES)
    else:
        templates = dict(_HARDCODED_TEMPLATES)

    # Apply pilot-scale override unless the template explicitly uses a custom
    # `names` list (in which case we respect whatever count the author set —
    # you can't procedurally generate names from a fixed pool beyond its size
    # without losing determinism).
    for tpl in templates.values():
        if "names" not in tpl or not tpl.get("names"):
            tpl["count"] = _PILOT_FARMERS_PER_STATION

    return templates


STATION_FARMER_TEMPLATES = _load_farmer_templates()


def _seed_rng(station_id: str, index: int) -> random.Random:
    h = hashlib.md5(f"{station_id}:{index}".encode()).hexdigest()
    return random.Random(int(h, 16))


def _make_phone(station_id: str, index: int, country_code: str = "+91") -> str:
    rng = _seed_rng(station_id, index)
    return f"{country_code}{rng.randint(7000000000, 9999999999)}"


def _make_aadhaar_id(station_id: str, index: int) -> str:
    rng = _seed_rng(station_id, index)
    last4 = rng.randint(1000, 9999)
    return f"XXXX-XXXX-{last4}"


class SimulatedDPIRegistry:
    """Pre-generates 40+ realistic farmers at import time. No DB dependency."""

    def __init__(self):
        self._farmers: Dict[str, FarmerProfile] = {}   # phone → profile
        self._by_aadhaar: Dict[str, FarmerProfile] = {}
        self._generate_all()

    def _generate_all(self):
        # Language → name pool mapping (hardcoded pools for ml/ta, custom via JSON)
        _name_pools: Dict[str, List] = {"ml": list(_ML_NAMES), "ta": list(_TA_NAMES)}
        _name_idx: Dict[str, int] = {}

        for station_id, tpl in STATION_FARMER_TEMPLATES.items():
            # If template has custom names (from farmers.json), use those
            custom_names = tpl.get("names")  # list of [en_name, local_name] pairs

            for i in range(tpl.get("count", 2)):
                rng = _seed_rng(station_id, i)
                phone = _make_phone(station_id, i)
                aadhaar_id = _make_aadhaar_id(station_id, i)

                lang = tpl.get("lang", "en")
                if custom_names and i < len(custom_names):
                    pair = custom_names[i]
                    name_en = pair[0]
                    name_local = pair[1] if len(pair) > 1 else pair[0]
                elif lang in _name_pools:
                    idx = _name_idx.get(lang, 0)
                    pool = _name_pools[lang]
                    name_en, name_local = pool[idx % len(pool)]
                    _name_idx[lang] = idx + 1
                else:
                    name_en = f"Farmer {station_id}_{i}"
                    name_local = name_en

                aadhaar = AadhaarProfile(
                    aadhaar_id=aadhaar_id, name=name_en, name_local=name_local,
                    phone=phone, district=tpl["district"], state=tpl["state"],
                    language=tpl["lang"], dob_year=rng.randint(1965, 1998),
                )

                from config import STATION_MAP
                st_cfg = STATION_MAP.get(station_id)
                lat_off = rng.uniform(-0.05, 0.05)
                lon_off = rng.uniform(-0.05, 0.05)

                area = round(rng.uniform(*tpl["area"]), 2)
                num_crops = rng.randint(1, min(3, len(tpl["crops"])))
                crops = rng.sample(tpl["crops"], num_crops)

                land = LandRecord(
                    survey_number=f"{rng.randint(100, 999)}/{rng.randint(1, 9)}{rng.choice('ABCDE')}",
                    area_hectares=area,
                    soil_type=rng.choice(tpl["soil"]),
                    irrigation_type=rng.choice(tpl["irrigation"]),
                    gps_lat=round(st_cfg.lat + lat_off, 4) if st_cfg else 10.0,
                    gps_lon=round(st_cfg.lon + lon_off, 4) if st_cfg else 76.0,
                    crops_registered=crops,
                    nearest_station_id=station_id,
                )

                pH = round(rng.uniform(*tpl["pH"]), 1)
                n_class = "low" if pH < 5.5 else ("high" if pH > 7.5 else "medium")
                soil = SoilHealthCard(
                    card_number=f"SHC-{tpl['district'][:3].upper()}-{rng.randint(10000, 99999)}",
                    pH=pH,
                    nitrogen_kg_ha=round(rng.uniform(120, 350), 0),
                    phosphorus_kg_ha=round(rng.uniform(8, 45), 0),
                    potassium_kg_ha=round(rng.uniform(80, 300), 0),
                    organic_carbon_pct=round(rng.uniform(0.3, 1.2), 2),
                    micronutrients={
                        "S": round(rng.uniform(5, 25), 1),
                        "Zn": round(rng.uniform(0.3, 2.5), 2),
                        "Fe": round(rng.uniform(2, 15), 1),
                        "Mn": round(rng.uniform(1, 10), 1),
                        "Cu": round(rng.uniform(0.2, 3.0), 2),
                        "B": round(rng.uniform(0.2, 1.5), 2),
                    },
                    classification=n_class,
                    recommendations=_soil_recommendations(pH, n_class, crops),
                )

                cat = "marginal" if area < 1.0 else ("small" if area < 2.0 else "semi-medium")
                installments = rng.randint(6, 18)
                pmkisan = PMKISANRecord(
                    beneficiary_id=f"PMKISAN-{tpl['state'][:2].upper()}-{rng.randint(100000, 999999)}",
                    holding_category=cat,
                    installments_received=installments,
                    total_amount=installments * 2000.0,
                    last_payment_date=f"2025-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
                    payment_history=[
                        {"installment": j + 1, "amount": 2000.0,
                         "date": f"{2020 + j // 3}-{(j % 12) + 1:02d}-15"}
                        for j in range(installments)
                    ],
                )

                insured = rng.sample(crops, min(2, len(crops)))
                sum_insured = round(area * rng.uniform(30000, 80000), 0)
                premium = round(sum_insured * rng.uniform(0.015, 0.05), 0)
                has_claim = rng.random() < 0.25
                pmfby = PMFBYRecord(
                    policy_id=f"PMFBY-{rng.randint(100000, 999999)}",
                    season=rng.choice(["kharif", "rabi"]),
                    insured_crops=insured,
                    sum_insured=sum_insured,
                    premium_paid=premium,
                    claim_history=[{
                        "year": 2024, "crop": insured[0],
                        "amount_claimed": round(sum_insured * 0.3, 0),
                        "amount_settled": round(sum_insured * 0.2, 0),
                        "status": "settled",
                    }] if has_claim else [],
                    status="active",
                )

                credit = round(area * rng.uniform(50000, 150000), 0)
                outstanding = round(credit * rng.uniform(0.1, 0.7), 0)
                kcc = KCCRecord(
                    kcc_number=f"KCC-{rng.randint(1000000, 9999999)}",
                    credit_limit=credit,
                    outstanding=outstanding,
                    crops_financed=crops,
                    repayment_status=rng.choice(["current", "current", "current", "overdue"]),
                    last_payment_date=f"2025-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
                )

                profile = FarmerProfile(
                    aadhaar=aadhaar, land_records=[land],
                    soil_health=soil, pmkisan=pmkisan,
                    pmfby=pmfby, kcc=kcc,
                )
                self._farmers[phone] = profile
                self._by_aadhaar[aadhaar_id] = profile

    # ----- public query API -----

    def lookup_by_phone(self, phone: str) -> Optional[FarmerProfile]:
        return self._farmers.get(phone)

    def lookup_by_aadhaar(self, aadhaar_id: str) -> Optional[FarmerProfile]:
        return self._by_aadhaar.get(aadhaar_id)

    def list_farmers(self) -> List[Dict[str, Any]]:
        return [
            {"phone": p.aadhaar.phone, "name": p.aadhaar.name,
             "district": p.aadhaar.district, "station": p.nearest_stations[0] if p.nearest_stations else "",
             "crops": p.primary_crops, "area_ha": p.total_area}
            for p in self._farmers.values()
        ]

    def get_aadhaar(self, phone: str) -> Optional[AadhaarProfile]:
        p = self._farmers.get(phone)
        return p.aadhaar if p else None

    def get_land_records(self, aadhaar_id: str) -> List[LandRecord]:
        p = self._by_aadhaar.get(aadhaar_id)
        return p.land_records if p else []

    def get_soil_health(self, aadhaar_id: str) -> Optional[SoilHealthCard]:
        p = self._by_aadhaar.get(aadhaar_id)
        return p.soil_health if p else None

    def get_pmkisan(self, aadhaar_id: str) -> Optional[PMKISANRecord]:
        p = self._by_aadhaar.get(aadhaar_id)
        return p.pmkisan if p else None

    def get_pmfby(self, aadhaar_id: str) -> Optional[PMFBYRecord]:
        p = self._by_aadhaar.get(aadhaar_id)
        return p.pmfby if p else None

    def get_kcc(self, aadhaar_id: str) -> Optional[KCCRecord]:
        p = self._by_aadhaar.get(aadhaar_id)
        return p.kcc if p else None

    @property
    def farmer_count(self) -> int:
        return len(self._farmers)


def _soil_recommendations(pH: float, classification: str, crops: List[str]) -> List[str]:
    recs = []
    if pH < 5.5:
        recs.append("Apply lime at 500-1000 kg/ha to correct soil acidity")
    elif pH > 7.5:
        recs.append("Apply gypsum at 2-4 tonnes/ha to reduce alkalinity")
    if classification == "low":
        recs.append("Increase nitrogen application by 25% above recommended dose")
    if "rice" in crops:
        recs.append("Apply zinc sulfate at 25 kg/ha for paddy")
    if "coffee" in crops or "pepper" in crops:
        recs.append("Maintain mulch cover to improve organic carbon")
    if not recs:
        recs.append("Continue balanced NPK application as per soil test values")
    return recs


# Singleton — pre-generated at import time
_registry: Optional[SimulatedDPIRegistry] = None


def get_registry() -> SimulatedDPIRegistry:
    global _registry
    if _registry is None:
        _registry = SimulatedDPIRegistry()
    return _registry
