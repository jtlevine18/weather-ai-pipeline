"""
Weather AI 2 — Kerala & Tamil Nadu dashboard homepage.
Run with: streamlit run streamlit_app/app.py
"""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st

# Auto-resume daily scheduler if previously enabled (survives HF Spaces restarts)
import src.daily_scheduler  # noqa: F401

from streamlit_app.style import inject_css, STATUS_COLOR
from streamlit_app.data_helpers import (
    load_pipeline_runs, load_station_health, load_pipeline_stage_stats,
)

st.set_page_config(
    page_title="Weather AI",
    page_icon="W",
    layout="wide",
)
inject_css()

# Hide auto sidebar nav (we build our own) + transparent header
st.markdown("""
<style>
    header[data-testid="stHeader"] {
        background: transparent !important;
    }
    [data-testid="stSidebarNav"] {
        display: none !important;
    }
    nav[data-testid="stSidebarNav"] {
        display: none !important;
    }
    /* Hide auto-generated sidebar nav links */
    [data-testid="stSidebar"] ul[data-testid="stSidebarNavItems"] {
        display: none !important;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    # Navigation — replaces auto-generated sidebar nav
    st.page_link("app.py", label="Home", icon="🏠")
    st.page_link("pages/1_Data.py", label="Data", icon="📡")
    st.page_link("pages/2_Forecasts.py", label="Forecasts", icon="🌦")
    st.page_link("pages/3_Advisories.py", label="Advisories", icon="🌾")
    st.page_link("pages/_System.py", label="System", icon="⚙")
    st.divider()

    health = load_station_health()
    if not health.empty:
        n_active = health["station_id"].nunique()
        avg_q = health["avg_quality"].mean() if "avg_quality" in health.columns else 0
        st.metric("Active Stations", f"{n_active}/20")
        st.metric("Avg Quality", f"{avg_q:.0%}")

# Chat toggle
from streamlit_app.chat_widget import render_chat_toggle
render_chat_toggle()

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
stats = load_pipeline_stage_stats()
runs = load_pipeline_runs(limit=10)

# ---------------------------------------------------------------------------
# Hero
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    .hero-title {
        margin: 0;
        font-weight: 700;
        color: #1a1a1a;
        font-family: DM Sans, sans-serif;
        letter-spacing: -0.5px;
        line-height: 1.25;
        font-size: 1.65rem;
    }
    .hero-sub {
        color: #999;
        line-height: 1.6;
        margin: 6px 0 0;
        font-family: DM Sans, sans-serif;
        font-size: 0.86rem;
    }
    @media (max-width: 900px) {
        .hero-title { font-size: 1.35rem; }
        .hero-sub { font-size: 0.82rem; }
    }
    @media (max-width: 640px) {
        .hero-title { font-size: 1.1rem; letter-spacing: -0.2px; }
        .hero-sub { font-size: 0.78rem; }
    }
</style>
<div style="padding:28px 0 8px;">
    <h1 class="hero-title">
        AI Weather Forecasts &amp; Farming Advisories<br/>
        <span style="color:#999;font-weight:400;">for Smallholder Farmers in Southern India</span>
    </h1>
    <p class="hero-sub">
        This system collects real weather data from 20 IMD stations across Kerala and Tamil Nadu,
        generates machine-learning-corrected forecasts personalized to each farmer's GPS location,
        and delivers crop-specific advisories in Tamil and Malayalam via SMS. Station observations
        are ingested daily, cross-validated for quality, then fed into forecast models that correct
        global weather predictions using local patterns. A RAG-powered AI generates farming advice
        based on each farmer's crops, soil, and upcoming weather, translates it into the local
        language, and delivers it by SMS.
    </p>
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# 3 clickable stage cards
# ---------------------------------------------------------------------------
# Compute readable stats for cards
_fc_total = stats.get("forecasts", 0)
_mos_total = stats.get("mos_count", 0)
_ml_pct = f"{100 * _mos_total // max(1, _fc_total)}%" if _fc_total else "—"

# Parse source names from the raw string (e.g. "imd_api:15 · imdlib:3")
_src_raw = stats.get("sources") or ""
_src_names = []
for chunk in _src_raw.split("·"):
    name = chunk.strip().split(":")[0].strip()
    if name == "imd_api":
        _src_names.append("IMD")
    elif name == "imdlib":
        _src_names.append("imdlib")
    elif name == "synthetic":
        _src_names.append("Synthetic")
    elif name:
        _src_names.append(name)
_src_label = ", ".join(_src_names) if _src_names else "—"

STAGES = [
    {
        "key": "data",
        "title": "Data",
        "href": "/Data",
        "icon": "📡",
        "color": "#2E7D32",
        "desc": ("Weather readings from 20 stations across Kerala and Tamil Nadu, "
                 "automatically cleaned and quality-checked"),
        "stats": [
            ("Stations", "20"),
            ("Data Sources", _src_label),
            ("Avg Quality", f"{stats.get('avg_quality', 0):.0%}"),
        ],
    },
    {
        "key": "forecasts",
        "title": "Forecasts",
        "href": "/Forecasts",
        "icon": "🌦️",
        "color": "#1565C0",
        "desc": ("7-day forecasts corrected with machine learning, "
                 "personalized to each farmer's location and elevation"),
        "stats": [
            ("Forecasts", str(_fc_total)),
            ("ML Model Used", _ml_pct),
        ],
    },
    {
        "key": "advisories",
        "title": "Advisories",
        "href": "/Advisories",
        "icon": "🌾",
        "color": "#d4a019",
        "desc": ("Crop-specific farming advice in Tamil and Malayalam, "
                 "generated daily and delivered by SMS"),
        "stats": [
            ("Advisories", str(stats.get("advisories", 0))),
            ("Delivered", str(stats.get("deliveries", 0))),
        ],
    },
]

# Arrow SVG
_arrow = (
    '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" '
    'stroke="#c8c0b4" stroke-width="1.5" stroke-linecap="round" '
    'stroke-linejoin="round"><polyline points="9 6 15 12 9 18"></polyline></svg>'
)

# Build all three cards + arrows as a single HTML block
cards_html = '<div style="display:flex;align-items:stretch;gap:0;max-width:100%;">'
for idx, stage in enumerate(STAGES):
    stats_html = "".join(
        f'<div style="display:flex;justify-content:space-between;padding:3px 0;">'
        f'<span style="color:#999;font-size:0.76rem;">{label}</span>'
        f'<span style="color:#1a1a1a;font-size:0.76rem;font-weight:600;">{val}</span>'
        f'</div>'
        for label, val in stage["stats"]
    )
    cards_html += f'''
    <a href="{stage['href']}" target="_self" class="stage-link">
        <div style="position:absolute;top:0;left:0;right:0;height:3px;
                    background:{stage['color']};border-radius:14px 14px 0 0;"></div>
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;">
            <div style="width:38px;height:38px;border-radius:10px;display:flex;
                        align-items:center;justify-content:center;font-size:1.1rem;
                        background:{stage['color']}12;flex-shrink:0;">{stage['icon']}</div>
            <div style="font-family:DM Sans,sans-serif;font-weight:600;
                        font-size:1.1rem;color:#1a1a1a;">{stage['title']}</div>
        </div>
        <div style="color:#888;font-size:0.78rem;line-height:1.55;margin-bottom:14px;
                    flex:1;">{stage['desc']}</div>
        <div style="border-top:1px solid #f0ede8;padding-top:10px;">
            {stats_html}
        </div>
    </a>
    '''
    if idx < 2:
        cards_html += (
            f'<div style="display:flex;align-items:center;padding:0 6px;">{_arrow}</div>'
        )

cards_html += '</div>'
st.markdown(cards_html, unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Key metrics
# ---------------------------------------------------------------------------
st.markdown("")
ok_runs = int((runs["status"] == "ok").sum()) if not runs.empty and "status" in runs.columns else 0

m1, m2, m3, m4 = st.columns(4)
m1.metric("Pipeline Runs", f"{ok_runs}/{len(runs)}")
m2.metric("Avg Quality", f"{stats.get('avg_quality', 0):.0%}")
m3.metric("Advisories", stats.get("advisories", 0))
m4.metric("Deliveries", stats.get("deliveries", 0))

# ---------------------------------------------------------------------------
# Run history
# ---------------------------------------------------------------------------
if not runs.empty:
    with st.expander("Run history"):
        run_html = ""
        for _, run in runs.head(8).iterrows():
            s = run.get("status", "?")
            run_id = str(run.get("id", ""))[:8]
            started = str(run.get("started_at", ""))[:16]
            summary = str(run.get("summary", ""))
            color = STATUS_COLOR.get(s, "#888")
            run_html += (
                f"<div style='display:flex;align-items:center;padding:8px 14px;"
                f"border-bottom:1px solid #f0ede8;gap:12px;font-size:0.8rem;"
                f"font-family:DM Sans,sans-serif;'>"
                f"<span style='background:{color};color:#fff;padding:2px 10px;border-radius:5px;"
                f"font-size:0.68rem;font-weight:700;min-width:50px;text-align:center;'>{s}</span>"
                f"<span style='color:#aaa;font-family:monospace;font-size:0.75rem;'>{run_id}</span>"
                f"<span style='color:#888;'>{started}</span>"
                f"<span style='color:#444;flex:1;'>{summary}</span>"
                f"</div>"
            )
        st.markdown(
            f'<div style="border:1px solid #e0dcd5;border-radius:10px;overflow:hidden;'
            f'background:#fff;">{run_html}</div>',
            unsafe_allow_html=True,
        )
