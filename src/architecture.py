"""
Dynamic Mermaid architecture diagram generator.
Used by both the Streamlit dashboard and the NL agent.
"""

from __future__ import annotations
from typing import Optional


def generate_mermaid() -> str:
    """
    Generate a Mermaid flowchart showing the live pipeline architecture.
    This is generated dynamically (not a static string) so it stays in sync.
    """
    return """flowchart TD
    subgraph INPUT["Data Sources (each API has ONE job)"]
        SYN[/"🔧 Synthetic Generator\\nFault injection"/]
        TIO[/"🌐 Tomorrow.io\\nReal-time reference"/]
        OMT[/"📡 Open-Meteo\\nGFS/ECMWF NWP"/]
        NAS[/"🛰️ NASA POWER\\nSpatial grid"/]
        CLD[/"🤖 Claude API\\nAdvisory + Translation"/]
    end

    subgraph PIPELINE["Pipeline (6 steps, linear)"]
        S1["Step 1: Ingest\\nraw_telemetry table"]
        S2["Step 2: Heal\\nAnomaly detection + imputation\\nclean_telemetry table"]
        S3["Step 3: Forecast\\nMOS: NWP + XGBoost residual\\nforecasts table"]
        S4["Step 4: Downscale\\nIDW interpolation + lapse-rate\\nFarmer GPS resolution"]
        S5["Step 5: Translate\\nRAG (FAISS+BM25) + Claude\\nagricultural_alerts table"]
        S6["Step 6: Deliver\\nConsole + SMS + WhatsApp\\ndelivery_log table"]
    end

    SYN -->|"synthetic readings"| S1
    S1 --> S2
    TIO -->|"cross-validation"| S2
    NAS -->|"offline imputation"| S2
    S2 --> S3
    OMT -->|"NWP baseline"| S3
    S3 --> S4
    NAS -->|"spatial grid"| S4
    S4 --> S5
    CLD -->|"English advisory"| S5
    CLD -->|"Translation"| S5
    S5 --> S6

    style S1 fill:#1e3a5f,color:#fff
    style S2 fill:#1e3a5f,color:#fff
    style S3 fill:#1e3a5f,color:#fff
    style S4 fill:#1e3a5f,color:#fff
    style S5 fill:#1e3a5f,color:#fff
    style S6 fill:#1e3a5f,color:#fff
"""


def get_architecture_text() -> str:
    """Return plain-text architecture description for the NL agent."""
    return """
Kerala/Tamil Nadu Weather Pipeline Architecture
===============================================

DATA SOURCES (each API has exactly one job):
  1. Synthetic Generator  → Step 1 Ingest  (simulates 20 ground stations with fault injection)
  2. Tomorrow.io          → Step 2 Heal    (independent reference for anomaly cross-validation)
  3. Open-Meteo           → Step 3 Forecast (GFS/ECMWF NWP baseline)
  4. NASA POWER           → Step 4 Downscale (25-cell spatial grid for IDW interpolation)
  5. Claude API           → Step 5 Translate (RAG advisory + language translation)

PIPELINE STEPS:
  Step 1 Ingest:     Generate synthetic readings for 20 stations. Store in raw_telemetry.
  Step 2 Heal:       Cross-validate vs Tomorrow.io. Fix typos, impute offline stations
                     from NASA POWER. If NASA also fails: skip (never fabricate).
                     Store in clean_telemetry.
  Step 3 Forecast:   Fetch Open-Meteo NWP. Train XGBoost on (obs - NWP) residuals.
                     Final = NWP + correction. Store in forecasts.
  Step 4 Downscale:  Fetch NASA POWER 5×5 grid (~0.5° radius). Apply IDW interpolation
                     to farmer GPS. Apply lapse-rate elevation correction. Re-classify
                     weather condition.
  Step 5 Translate:  RAG retrieval (FAISS dense + BM25 sparse, α=0.5). Generate English
                     advisory via Claude. Separate Claude call to translate. Store in
                     agricultural_alerts.
  Step 6 Deliver:    Console (always), SMS/WhatsApp (dry-run unless --live-delivery).
                     Store in delivery_log.

DEGRADATION CHAIN (independent, never cascades):
  - NWP unavailable → persistence model (last obs + diurnal)
  - XGBoost not trained → raw NWP passthrough
  - Claude down → rule-based template advisories
  - Tomorrow.io down → skip healing (pass raw through)
  - NASA POWER down (heal) → skip that record
  - NASA POWER down (downscale) → use station forecast
  - Translation fails → return English advisory

STATIONS: 10 in Kerala, 10 in Tamil Nadu
LANGUAGES: Malayalam (ml) for Kerala, Tamil (ta) for Tamil Nadu
DATABASE: DuckDB embedded (weather.duckdb) — 6 tables
"""
