"""Centralized configuration for the Kerala/Tamil Nadu weather pipeline."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List
import json
import os
from dotenv import load_dotenv

load_dotenv()


@dataclass
class StationConfig:
    station_id: str
    name: str
    lat: float
    lon: float
    altitude_m: float
    state: str
    crop_context: str
    language: str  # "ta", "ml", "en"
    imd_id: str = ""  # WMO SYNOP station ID for IMD scraping


@dataclass
class FaultInjectionConfig:
    typo_rate: float = 0.05       # decimal-place errors
    offline_rate: float = 0.05    # station offline
    drift_rate: float = 0.05      # sensor drift
    missing_rate: float = 0.05    # missing fields


@dataclass
class DeliveryConfig:
    twilio_account_sid: str = field(default_factory=lambda: os.getenv("TWILIO_ACCOUNT_SID", ""))
    twilio_auth_token: str = field(default_factory=lambda: os.getenv("TWILIO_AUTH_TOKEN", ""))
    twilio_from: str = field(default_factory=lambda: os.getenv("TWILIO_FROM", "+15005550006"))
    live_delivery: bool = False


@dataclass
class TranslationConfig:
    model: str = "claude-sonnet-4-6"
    score_threshold: float = 0.35
    top_k: int = 5
    alpha: float = 0.5  # FAISS/BM25 blend weight


@dataclass
class WeatherDataConfig:
    fault_config: FaultInjectionConfig = field(default_factory=FaultInjectionConfig)
    ingestion_source: str = "real"       # "real" or "synthetic"
    imd_cache_ttl_s: int = 1800          # 30-min cache for IMD scrapes


@dataclass
class NeuralGCMConfig:
    enabled: bool = True                            # On by default; falls back to Open-Meteo if no GPU
    model_name: str = "deterministic_2_8_deg"       # 2.8° resolution — fits in 24GB VRAM (L4/A100)
    forecast_hours: int = 168                       # 7-day forecast horizon


@dataclass
class DPIConfig:
    simulation: bool = True   # True = use simulated DPI registry, False = real APIs


@dataclass
class PipelineConfig:
    weather: WeatherDataConfig = field(default_factory=WeatherDataConfig)
    delivery: DeliveryConfig = field(default_factory=DeliveryConfig)
    translation: TranslationConfig = field(default_factory=TranslationConfig)
    neuralgcm: NeuralGCMConfig = field(default_factory=NeuralGCMConfig)
    dpi: DPIConfig = field(default_factory=DPIConfig)
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", ""))
    tomorrow_io_key: str = field(default_factory=lambda: os.getenv("TOMORROW_IO_API_KEY", ""))
    anthropic_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", "").strip())
    models_dir: str = "models"


# ---------------------------------------------------------------------------
# Station registry — loaded from stations.json (fallback to hardcoded)
# ---------------------------------------------------------------------------

_STATIONS_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stations.json")

_HARDCODED_STATIONS: List[StationConfig] = [
    # Kerala — coastal
    StationConfig("KL_TVM", "Thiruvananthapuram", 8.4833, 76.9500, 60,  "Kerala",
                  "coconut, rubber, banana, tapioca, pepper", "ml", "43371"),
    StationConfig("KL_COK", "Kochi",              9.9500, 76.2667, 1,   "Kerala",
                  "coconut, rubber, pineapple, nutmeg, banana", "ml", "43353"),
    StationConfig("KL_ALP", "Alappuzha",          9.5500, 76.4167, 2,   "Kerala",
                  "rice (paddy), coconut, banana, tapioca", "ml", "43352"),
    StationConfig("KL_KNR", "Kannur",            11.8333, 75.3333, 11,  "Kerala",
                  "coconut, cashew, pepper, rubber, arecanut", "ml", "43315"),
    StationConfig("KL_KZD", "Kozhikode",         11.2500, 75.7833, 4,   "Kerala",
                  "coconut, pepper, arecanut, rubber, banana", "ml", "43314"),
    # Kerala — midland
    StationConfig("KL_TCR", "Thrissur",          10.5167, 76.2167, 40,  "Kerala",
                  "rice (paddy), coconut, arecanut", "ml", "43357"),
    StationConfig("KL_KTM", "Kottayam",           9.5833, 76.5167, 39,  "Kerala",
                  "rubber, coconut, pepper, banana, cardamom", "ml", "43355"),
    StationConfig("KL_PKD", "Palakkad",          10.7667, 76.6500, 95,  "Kerala",
                  "rice (paddy), coconut, groundnut, arecanut, banana", "ml", "43335"),
    # Kerala — Kollam district (Punalur replaces Kollam city — has IMD SYNOP station)
    StationConfig("KL_PNL", "Punalur",            9.0000, 76.9167, 33,  "Kerala",
                  "rubber, coconut, cashew, pepper, tapioca", "ml", "43354"),
    # Kerala — foothills (Nilambur replaces Wayanad — nearest IMD station)
    StationConfig("KL_NLB", "Nilambur",          11.2800, 76.2300, 30,  "Kerala",
                  "coconut, rubber, arecanut, pepper, paddy", "ml", "43316"),
    # Tamil Nadu — delta
    StationConfig("TN_TNJ", "Thanjavur",         10.7833, 79.1333, 0,   "Tamil Nadu",
                  "rice (paddy), pulses (black gram), sugarcane, banana, coconut", "ta", "43330"),
    # Tamil Nadu — dry zone
    StationConfig("TN_MDU", "Madurai",            9.8333, 78.0833, 139, "Tamil Nadu",
                  "paddy, cotton, groundnut, millets, banana", "ta", "43360"),
    StationConfig("TN_TRZ", "Tiruchirappalli",   10.7667, 78.7167, 85,  "Tamil Nadu",
                  "paddy, banana, sugarcane, groundnut, maize", "ta", "43344"),
    StationConfig("TN_SLM", "Salem",             11.6500, 78.1667, 279, "Tamil Nadu",
                  "tapioca, paddy, groundnut, maize, turmeric", "ta", "43325"),
    StationConfig("TN_ERD", "Erode",             11.3400, 77.7200, 183, "Tamil Nadu",
                  "turmeric, sugarcane, coconut, cotton, groundnut", "ta", "43338"),
    # Tamil Nadu — coastal
    StationConfig("TN_CHN", "Chennai",           13.0000, 80.1833, 10,  "Tamil Nadu",
                  "rice (paddy), vegetables, flowers", "ta", "43279"),
    StationConfig("TN_TNV", "Tirunelveli",        8.7333, 77.7500, 45,  "Tamil Nadu",
                  "paddy, banana, coconut, cotton, sugarcane", "ta", "43376"),
    # Tamil Nadu — western
    StationConfig("TN_CBE", "Coimbatore",        11.0333, 77.0500, 396, "Tamil Nadu",
                  "coconut, cotton, sugarcane, millets, groundnut", "ta", "43321"),
    StationConfig("TN_VLR", "Vellore",           12.9200, 79.1300, 215, "Tamil Nadu",
                  "paddy, groundnut, sugarcane, ragi, mango", "ta", "43303"),
    # Tamil Nadu — Bay of Bengal coast (Nagappattinam replaces Dindigul — has IMD station)
    StationConfig("TN_NGP", "Nagappattinam",     10.7667, 79.8500, 2,   "Tamil Nadu",
                  "rice (paddy), pulses (black gram), coconut, banana", "ta", "43347"),
]


def _load_stations() -> List[StationConfig]:
    """Load stations from stations.json if it exists, otherwise use hardcoded list."""
    if os.path.exists(_STATIONS_JSON):
        try:
            with open(_STATIONS_JSON) as f:
                data = json.load(f)
            return [
                StationConfig(
                    station_id=s["station_id"],
                    name=s["name"],
                    lat=s["lat"],
                    lon=s["lon"],
                    altitude_m=s["altitude_m"],
                    state=s["state"],
                    crop_context=s["crop_context"],
                    language=s["language"],
                    imd_id=s.get("imd_id", ""),
                )
                for s in data
            ]
        except Exception:
            pass  # Fall through to hardcoded
    return list(_HARDCODED_STATIONS)


STATIONS: List[StationConfig] = _load_stations()

STATION_MAP = {s.station_id: s for s in STATIONS}


def get_config() -> PipelineConfig:
    return PipelineConfig()
