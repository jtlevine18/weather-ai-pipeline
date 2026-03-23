"""
Weather AI 2 — Kerala & Tamil Nadu dashboard homepage.
Run with: streamlit run streamlit_app/app.py
"""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import pandas as pd
from datetime import datetime

from streamlit_app.style       import inject_css, CONDITION_EMOJI, CONDITION_COLOR
from streamlit_app.data_helpers import (load_forecasts, load_alerts, load_pipeline_runs,
                                         get_station_coords)

st.set_page_config(
    page_title="Weather AI — Kerala & Tamil Nadu",
    page_icon="🌾",
    layout="wide",
)
inject_css()

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("## 🌾 Weather AI")
    st.caption("Kerala & Tamil Nadu · Smallholder Farming")
    st.divider()

    # Pipeline trigger
    can_run = True  # extend with RBAC if needed
    if st.button("▶ Run Pipeline Now", width="stretch"):
        with st.spinner("Running pipeline…"):
            try:
                import asyncio
                from config import get_config
                from src.pipeline import WeatherPipeline
                config = get_config()
                pipeline = WeatherPipeline(config)
                result = asyncio.run(pipeline.run())
                st.success(f"{result['alerts']} alerts · {result['elapsed_s']:.0f}s")
                st.cache_data.clear()
                st.rerun()
            except Exception as exc:
                st.error(f"Pipeline error: {exc}")

    st.divider()

    # Station health mini-metrics
    from streamlit_app.data_helpers import load_station_health
    health = load_station_health()
    if not health.empty:
        n_stations = 20
        n_active   = health["station_id"].nunique()
        st.metric("Active Stations", f"{n_active}/{n_stations}")
        avg_q = health["avg_quality"].mean() if "avg_quality" in health.columns else 0
        st.metric("Avg Data Quality", f"{avg_q:.0%}")

    st.divider()
    if st.button("🔄 Refresh", width="stretch"):
        st.cache_data.clear()
        st.rerun()

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.header("Weather AI Pipeline")
st.caption("Agentic weather forecasting for smallholder farmers in Kerala and Tamil Nadu")

forecasts = load_forecasts(limit=200)
alerts    = load_alerts(limit=100)
runs      = load_pipeline_runs(limit=10)

# Key metrics row
m1, m2, m3, m4 = st.columns(4)

ok_runs = int((runs["status"] == "ok").sum()) if not runs.empty and "status" in runs.columns else 0
m1.metric("Pipeline Runs", len(runs), delta=f"{ok_runs} successful")
m2.metric("Forecasts", len(forecasts))
m3.metric("Advisories Sent", len(alerts))

if not forecasts.empty and "condition" in forecasts.columns:
    top_cond = forecasts["condition"].value_counts().index[0]
    emoji    = CONDITION_EMOJI.get(top_cond, "🌤️")
    m4.metric("Top Condition", f"{emoji} {top_cond.replace('_',' ').title()}")
else:
    m4.metric("Top Condition", "—")

st.divider()

STATION_NAMES = {s["station_id"]: s["name"] for _, s in get_station_coords().iterrows()}
COND_ICONS    = CONDITION_EMOJI

# ---------------------------------------------------------------------------
# Two-column: forecasts left, alerts right
# ---------------------------------------------------------------------------
col_fc, col_al = st.columns(2)

with col_fc:
    st.markdown('<div class="section-header">Latest Forecasts</div>', unsafe_allow_html=True)

    if forecasts.empty:
        st.info("No forecasts yet. Click **▶ Run Pipeline Now** to generate data.")
    else:
        latest = (forecasts.sort_values("issued_at", ascending=False)
                  .drop_duplicates(subset="station_id", keep="first")
                  .sort_values("station_id"))

        rows_html = ""
        for _, row in latest.iterrows():
            sid   = row.get("station_id", "?")
            name  = STATION_NAMES.get(sid, sid)
            cond  = row.get("condition", "clear")
            icon  = COND_ICONS.get(cond, "🌤️")
            temp  = row.get("temperature")
            rain  = row.get("rainfall")
            model = row.get("model_used", "—")
            color = CONDITION_COLOR.get(cond, "#666")

            temp_str = f"{temp:.1f}°C" if temp is not None else "—"
            rain_str = f"{rain:.1f}mm" if rain is not None else "—"
            model_badge_color = "#2a9d8f" if model == "hybrid_mos" else "#888"

            rows_html += f"""
            <div style="display:flex;align-items:center;padding:8px 12px;
                        border-bottom:1px solid #f0ede8;gap:10px;">
              <span style="font-size:1.2rem;">{icon}</span>
              <div style="flex:1;min-width:0;">
                <span style="font-weight:600;color:#1a1a1a;">{name}</span>
                <span style="color:#999;font-size:0.75rem;margin-left:6px;">{sid}</span>
              </div>
              <span style="background:{color};color:white;padding:2px 7px;border-radius:4px;
                           font-size:0.7rem;font-weight:600;">{cond.replace('_',' ')}</span>
              <span style="color:#333;font-size:0.85rem;width:55px;text-align:right;">{temp_str}</span>
              <span style="color:#666;font-size:0.8rem;width:45px;text-align:right;">{rain_str}</span>
              <span style="background:{model_badge_color};color:#fff;padding:1px 6px;border-radius:3px;
                           font-size:0.65rem;">{model}</span>
            </div>"""

        st.markdown(
            f'<div style="border:1px solid #e0dcd5;border-radius:8px;overflow:hidden;">{rows_html}</div>',
            unsafe_allow_html=True,
        )

with col_al:
    st.markdown('<div class="section-header">Recent Advisories</div>', unsafe_allow_html=True)

    if alerts.empty:
        st.info("No advisories yet.")
    else:
        priority_colors = {"critical": "#e63946", "high": "#f4a261",
                           "medium": "#d4a019", "low": "#2a9d8f"}
        for _, alert in alerts.head(12).iterrows():
            cond     = alert.get("condition", "clear")
            icon     = COND_ICONS.get(cond, "📋")
            sid      = alert.get("station_id", "?")
            name     = STATION_NAMES.get(sid, sid)
            lang     = alert.get("language", "en")
            prov     = alert.get("provider", "?")
            advisory = str(alert.get("advisory_local") or alert.get("advisory_en", ""))
            color    = CONDITION_COLOR.get(cond, "#666")
            prov_label = "🤖 RAG" if prov == "rag_claude" else "📋 Rule"

            st.markdown(
                f"""<div style="border:1px solid #e0dcd5;border-radius:8px;padding:10px 14px;
                    margin-bottom:6px;background:#fff;">
                  <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
                    <span style="font-size:1.1rem;">{icon}</span>
                    <strong style="color:#1a1a1a;">{name}</strong>
                    <span style="background:{color};color:white;padding:2px 7px;border-radius:4px;
                                 font-size:0.7rem;font-weight:600;">{cond.replace('_',' ')}</span>
                    <span style="margin-left:auto;color:#888;font-size:0.7rem;">{prov_label} · {lang}</span>
                  </div>
                  <div style="color:#555;font-size:0.82rem;line-height:1.4;">
                    {advisory[:140]}{"…" if len(advisory) > 140 else ""}
                  </div>
                </div>""",
                unsafe_allow_html=True,
            )

# ---------------------------------------------------------------------------
# Recent pipeline runs
# ---------------------------------------------------------------------------
st.divider()
st.markdown('<div class="section-header">Pipeline Run History</div>', unsafe_allow_html=True)

if runs.empty:
    st.info("No pipeline runs yet. Click **▶ Run Pipeline Now** in the sidebar.")
else:
    STATUS_COLOR = {"ok": "#2a9d8f", "partial": "#f4a261", "failed": "#e63946", "running": "#1976D2"}
    run_html = ""
    for _, run in runs.head(8).iterrows():
        status  = run.get("status", "?")
        run_id  = str(run.get("id", ""))[:8]
        started = str(run.get("started_at", ""))[:16]
        summary = str(run.get("summary", ""))
        color   = STATUS_COLOR.get(status, "#888")
        run_html += (
            f"<div style='display:flex;align-items:center;padding:7px 12px;"
            f"border-bottom:1px solid #f0ede8;gap:10px;font-size:0.82rem;'>"
            f"<span style='background:{color};color:#fff;padding:1px 8px;border-radius:3px;"
            f"font-size:0.7rem;font-weight:600;min-width:55px;text-align:center'>{status}</span>"
            f"<span style='color:#888;font-family:monospace'>{run_id}</span>"
            f"<span style='color:#666'>{started}</span>"
            f"<span style='color:#333;flex:1'>{summary}</span>"
            f"</div>"
        )
    st.markdown(
        f'<div style="border:1px solid #e0dcd5;border-radius:8px;overflow:hidden;">{run_html}</div>',
        unsafe_allow_html=True,
    )
