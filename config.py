"""Centralized configuration for the Kerala/Tamil Nadu weather pipeline."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List
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


@dataclass
class PipelineConfig:
    weather: WeatherDataConfig = field(default_factory=WeatherDataConfig)
    delivery: DeliveryConfig = field(default_factory=DeliveryConfig)
    translation: TranslationConfig = field(default_factory=TranslationConfig)
    db_path: str = "weather.duckdb"
    tomorrow_io_key: str = field(default_factory=lambda: os.getenv("TOMORROW_IO_API_KEY", ""))
    anthropic_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", "").strip())
    models_dir: str = "models"


# ---------------------------------------------------------------------------
# Station registry
# ---------------------------------------------------------------------------

STATIONS: List[StationConfig] = [
    # Kerala — coastal
    StationConfig("KL_TVM", "Thiruvananthapuram", 8.5241, 76.9366, 64,  "Kerala", "coconut, rubber, banana, tapioca", "ml"),
    StationConfig("KL_COK", "Kochi",              9.9312, 76.2673, 6,   "Kerala", "coconut, rubber, banana, tapioca", "ml"),
    StationConfig("KL_KLM", "Kollam",             8.8932, 76.6141, 11,  "Kerala", "coconut, rubber, banana, tapioca", "ml"),
    StationConfig("KL_ALP", "Alappuzha",          9.4981, 76.3388, 1,   "Kerala", "coconut, rubber, banana, tapioca", "ml"),
    StationConfig("KL_KNR", "Kannur",            11.8745, 75.3704, 31,  "Kerala", "coconut, rubber, banana, tapioca", "ml"),
    # Kerala — midland
    StationConfig("KL_TCR", "Thrissur",          10.5276, 76.2144, 2,   "Kerala", "rice (paddy), coconut, arecanut", "ml"),
    StationConfig("KL_KTM", "Kottayam",           9.5916, 76.5222, 4,   "Kerala", "rice (paddy), coconut, arecanut", "ml"),
    StationConfig("KL_PKD", "Palakkad",          10.7867, 76.6548, 79,  "Kerala", "rice (paddy), coconut, arecanut", "ml"),
    StationConfig("KL_KZD", "Kozhikode",         11.2588, 75.7804, 10,  "Kerala", "coconut, rubber, banana, tapioca", "ml"),
    # Kerala — highland
    StationConfig("KL_WYD", "Wayanad",           11.6854, 76.1320, 780, "Kerala", "coffee, pepper, cardamom, tea", "ml"),
    # Tamil Nadu — delta
    StationConfig("TN_TNJ", "Thanjavur",         10.7870, 79.1378, 60,  "Tamil Nadu", "rice (Cauvery delta)", "ta"),
    # Tamil Nadu — dry zone
    StationConfig("TN_MDU", "Madurai",            9.9252, 78.1198, 101, "Tamil Nadu", "cotton, millets, groundnut, sugarcane", "ta"),
    StationConfig("TN_TRZ", "Tiruchirappalli",   10.7905, 78.7047, 88,  "Tamil Nadu", "cotton, millets, groundnut, sugarcane", "ta"),
    StationConfig("TN_DGL", "Dindigul",          10.3673, 77.9803, 290, "Tamil Nadu", "cotton, millets, groundnut, sugarcane", "ta"),
    StationConfig("TN_SLM", "Salem",             11.6643, 78.1460, 280, "Tamil Nadu", "cotton, millets, groundnut, sugarcane", "ta"),
    StationConfig("TN_ERD", "Erode",             11.3410, 77.7172, 183, "Tamil Nadu", "cotton, millets, groundnut, sugarcane", "ta"),
    # Tamil Nadu — coastal
    StationConfig("TN_CHN", "Chennai",           13.0827, 80.2707, 7,   "Tamil Nadu", "rice, banana, cashew", "ta"),
    StationConfig("TN_TNV", "Tirunelveli",        8.7139, 77.7567, 60,  "Tamil Nadu", "rice, banana, cashew", "ta"),
    # Tamil Nadu — western
    StationConfig("TN_CBE", "Coimbatore",        11.0168, 76.9558, 427, "Tamil Nadu", "turmeric, sugarcane, vegetables", "ta"),
    StationConfig("TN_VLR", "Vellore",           12.9165, 79.1325, 215, "Tamil Nadu", "turmeric, sugarcane, vegetables", "ta"),
]

STATION_MAP = {s.station_id: s for s in STATIONS}


def get_config() -> PipelineConfig:
    return PipelineConfig()
