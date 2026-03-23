"""Dataclasses mirroring Indian Digital Public Infrastructure schemas."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class AadhaarProfile:
    aadhaar_id: str          # masked: XXXX-XXXX-1234
    name: str
    name_local: str          # in Tamil/Malayalam script
    phone: str
    district: str
    state: str
    language: str            # "ta", "ml", "en"
    dob_year: int = 1980


@dataclass
class LandRecord:
    survey_number: str
    area_hectares: float
    soil_type: str
    irrigation_type: str
    gps_lat: float
    gps_lon: float
    crops_registered: List[str] = field(default_factory=list)
    nearest_station_id: str = ""


@dataclass
class SoilHealthCard:
    card_number: str
    pH: float
    nitrogen_kg_ha: float
    phosphorus_kg_ha: float
    potassium_kg_ha: float
    organic_carbon_pct: float
    micronutrients: Dict[str, float] = field(default_factory=dict)  # S, Zn, Fe, Mn, Cu, B
    classification: str = "medium"      # low/medium/high
    recommendations: List[str] = field(default_factory=list)


@dataclass
class PMKISANRecord:
    beneficiary_id: str
    holding_category: str    # marginal (<1ha), small (1-2ha), semi-medium (2-4ha)
    installments_received: int
    total_amount: float
    last_payment_date: str
    payment_history: List[Dict] = field(default_factory=list)


@dataclass
class PMFBYRecord:
    policy_id: str
    season: str              # kharif / rabi
    insured_crops: List[str] = field(default_factory=list)
    sum_insured: float = 0.0
    premium_paid: float = 0.0
    claim_history: List[Dict] = field(default_factory=list)
    status: str = "active"


@dataclass
class KCCRecord:
    kcc_number: str
    credit_limit: float
    outstanding: float
    crops_financed: List[str] = field(default_factory=list)
    repayment_status: str = "current"  # current / overdue / defaulted
    last_payment_date: str = ""


@dataclass
class FarmerProfile:
    """Composite profile assembled by DPIAgent from all DPI sources."""
    aadhaar: AadhaarProfile
    land_records: List[LandRecord] = field(default_factory=list)
    soil_health: Optional[SoilHealthCard] = None
    pmkisan: Optional[PMKISANRecord] = None
    pmfby: Optional[PMFBYRecord] = None
    kcc: Optional[KCCRecord] = None

    @property
    def total_area(self) -> float:
        return sum(lr.area_hectares for lr in self.land_records)

    @property
    def primary_crops(self) -> List[str]:
        crops = []
        for lr in self.land_records:
            crops.extend(lr.crops_registered)
        return list(dict.fromkeys(crops))  # dedupe preserving order

    @property
    def nearest_stations(self) -> List[str]:
        return list({lr.nearest_station_id for lr in self.land_records if lr.nearest_station_id})

    @property
    def soil_summary(self) -> str:
        if not self.soil_health:
            return "No soil health data"
        sh = self.soil_health
        return (f"pH {sh.pH:.1f}, N/P/K {sh.nitrogen_kg_ha:.0f}/{sh.phosphorus_kg_ha:.0f}/"
                f"{sh.potassium_kg_ha:.0f} kg/ha, OC {sh.organic_carbon_pct:.1f}%")

    @property
    def financial_capacity(self) -> str:
        parts = []
        if self.pmkisan:
            parts.append(f"PM-KISAN: {self.pmkisan.installments_received} installments")
        if self.kcc:
            util = (self.kcc.outstanding / self.kcc.credit_limit * 100) if self.kcc.credit_limit > 0 else 0
            parts.append(f"KCC: {util:.0f}% utilized")
        if self.pmfby:
            parts.append(f"Insurance: {self.pmfby.status}")
        return "; ".join(parts) if parts else "No financial data"
