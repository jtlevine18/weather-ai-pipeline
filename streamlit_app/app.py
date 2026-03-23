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

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### Weather AI")
    st.caption("Kerala & Tamil Nadu")
    st.divider()

    health = load_station_health()
    if not health.empty:
        n_active = health["station_id"].nunique()
        avg_q = health["avg_quality"].mean() if "avg_quality" in health.columns else 0
        st.metric("Active Stations", f"{n_active}/20")
        st.metric("Avg Quality", f"{avg_q:.0%}")

    st.divider()
    if st.button("Refresh", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    # System link (de-emphasised)
    st.divider()
    st.page_link("pages/_4_System.py", label="System", icon="⚙")

# Chat toggle
from streamlit_app.chat_widget import render_chat_toggle
render_chat_toggle()

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.markdown("""
<div style="text-align:center;padding:20px 0 4px;">
    <h1 style="margin:0;font-size:2rem;font-weight:700;color:#1a1a1a;letter-spacing:-0.5px;">
        Weather AI
    </h1>
    <p style="color:#666;font-size:0.95rem;margin:4px 0 0;">
        Agentic weather forecasting for smallholder farmers in Kerala and Tamil Nadu
    </p>
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Pipeline diagram (clickable)
# ---------------------------------------------------------------------------
stats = load_pipeline_stage_stats()

from src.architecture import get_pipeline_stages
stages = get_pipeline_stages()

# Live stats for each stage
stage_stats = {
    "Ingest":    stats.get("sources", "no data") or "no data",
    "Heal":      f"avg quality {stats.get('avg_quality', 0):.0%}" if stats.get("avg_quality") else "no data",
    "Forecast":  f"{stats.get('mos_count', 0)} MOS" if stats.get("forecasts") else "no data",
    "Downscale": f"{stats.get('forecasts', 0)} forecasts",
    "Translate": f"{stats.get('advisories', 0)} advisories",
    "Deliver":   f"{stats.get('deliveries', 0)} delivered",
}

st.markdown("")

# Build the 6-stage + 5-arrow column layout
cols = st.columns([1, 0.2, 1, 0.2, 1, 0.2, 1, 0.2, 1, 0.2, 1])

for i, stage in enumerate(stages):
    with cols[i * 2]:
        stat_text = stage_stats.get(stage["name"], "")
        st.markdown(f"""
        <div class="pipeline-card">
            <div class="card-title">{stage["name"]}</div>
            <div class="card-stat">{stat_text}</div>
        </div>
        """, unsafe_allow_html=True)
        st.page_link(stage["page"], label=stage["desc"], use_container_width=True)
    if i < 5:
        with cols[i * 2 + 1]:
            st.markdown('<div class="pipeline-arrow">&rarr;</div>', unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Key stats
# ---------------------------------------------------------------------------
st.markdown("")
m1, m2, m3, m4 = st.columns(4)

runs = load_pipeline_runs(limit=10)
ok_runs = int((runs["status"] == "ok").sum()) if not runs.empty and "status" in runs.columns else 0
m1.metric("Pipeline Runs", len(runs), delta=f"{ok_runs} successful")
m2.metric("Data Freshness", f"quality {stats.get('avg_quality', 0):.0%}")
m3.metric("Advisories", stats.get("advisories", 0))
m4.metric("Deliveries", stats.get("deliveries", 0))

# ---------------------------------------------------------------------------
# Latest run summary
# ---------------------------------------------------------------------------
st.divider()

last_run = stats.get("last_run")
if last_run:
    st.markdown('<div class="section-header">Latest Run</div>', unsafe_allow_html=True)
    status = last_run.get("status", "?")
    summary = last_run.get("summary", "")
    started = str(last_run.get("time", ""))[:19]
    color = STATUS_COLOR.get(status, "#888")
    st.markdown(f"""
    <div style="display:flex;align-items:center;gap:12px;padding:10px 14px;
                background:#fff;border:1px solid #e0dcd5;border-radius:8px;">
        <span style="background:{color};color:#fff;padding:2px 10px;border-radius:4px;
                     font-size:0.75rem;font-weight:600;">{status}</span>
        <span style="color:#888;font-size:0.8rem;">{started}</span>
        <span style="color:#333;font-size:0.85rem;flex:1;">{summary}</span>
    </div>
    """, unsafe_allow_html=True)
else:
    st.info("No pipeline runs yet. Use the Manual Run button below to generate data.")

# Pipeline run history (compact)
if not runs.empty:
    with st.expander("Run history"):
        run_html = ""
        for _, run in runs.head(8).iterrows():
            status = run.get("status", "?")
            run_id = str(run.get("id", ""))[:8]
            started = str(run.get("started_at", ""))[:16]
            summary = str(run.get("summary", ""))
            color = STATUS_COLOR.get(status, "#888")
            run_html += (
                f"<div style='display:flex;align-items:center;padding:6px 12px;"
                f"border-bottom:1px solid #f0ede8;gap:10px;font-size:0.8rem;'>"
                f"<span style='background:{color};color:#fff;padding:1px 8px;border-radius:3px;"
                f"font-size:0.68rem;font-weight:600;min-width:50px;text-align:center'>{status}</span>"
                f"<span style='color:#888;font-family:monospace'>{run_id}</span>"
                f"<span style='color:#666'>{started}</span>"
                f"<span style='color:#333;flex:1'>{summary}</span>"
                f"</div>"
            )
        st.markdown(
            f'<div style="border:1px solid #e0dcd5;border-radius:8px;overflow:hidden;">{run_html}</div>',
            unsafe_allow_html=True,
        )

