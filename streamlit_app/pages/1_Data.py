"""Data page — Ingestion and Healing pipeline stages."""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import streamlit as st
import pandas as pd

from streamlit_app.style import inject_css
from streamlit_app.data_helpers import (
    get_station_coords, get_station_name_map, load_station_health,
    load_raw_telemetry, load_clean_telemetry,
    load_data_source_distribution, load_per_station_source,
)

st.set_page_config(page_title="Data", page_icon="D", layout="wide")
inject_css()

st.title("Data")
st.caption("Ingestion and healing pipeline — 20 stations across Kerala and Tamil Nadu")

stations = get_station_coords()
health = load_station_health()

# Merge health data
if not health.empty and "station_id" in health.columns:
    stations = stations.merge(health, on="station_id", how="left")
    stations["record_count"] = stations["record_count"].fillna(0).astype(int)
    stations["avg_quality"] = stations["avg_quality"].fillna(0.0)
else:
    stations["record_count"] = 0
    stations["avg_quality"] = 0.0

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_map, tab_sources, tab_healing, tab_health = st.tabs(
    ["Map", "Sources", "Healing", "Station Health"]
)

# ========================== MAP ==========================
with tab_map:
    def _color(row):
        if row["record_count"] == 0:
            return [200, 50, 50, 200]
        elif row.get("avg_quality", 1.0) < 0.7:
            return [255, 165, 0, 200]
        return [50, 200, 50, 200]

    map_df = stations.copy()
    map_df["color"] = map_df.apply(_color, axis=1)
    map_df["radius"] = 8000

    try:
        import pydeck as pdk

        layer = pdk.Layer(
            "ScatterplotLayer",
            data=map_df,
            get_position=["lon", "lat"],
            get_color="color",
            get_radius="radius",
            pickable=True,
            auto_highlight=True,
        )
        view = pdk.ViewState(latitude=10.5, longitude=78.0, zoom=5.5, pitch=0)
        tooltip = {
            "html": "<b>{name}</b><br/>State: {state}<br/>Crops: {crop}<br/>"
                    "Records: {record_count}<br/>Avg Quality: {avg_quality:.2f}",
            "style": {"backgroundColor": "#1a1a1a", "color": "white"},
        }
        st.pydeck_chart(pdk.Deck(
            layers=[layer],
            initial_view_state=view,
            tooltip=tooltip,
            map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
        ))
    except Exception as exc:
        st.warning(f"Map unavailable: {exc}")
        st.map(stations[["lat", "lon"]])

    # Legend
    st.markdown(
        '<div style="display:flex;gap:16px;margin-top:8px;font-size:0.8rem;color:#666;">'
        '<span><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:rgb(50,200,50);margin-right:4px;"></span>Good data</span>'
        '<span><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:rgb(255,165,0);margin-right:4px;"></span>Low quality</span>'
        '<span><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:rgb(200,50,50);margin-right:4px;"></span>No data</span>'
        '</div>',
        unsafe_allow_html=True,
    )

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
    show_cols = [c for c in [
        "station_id", "name", "state", "altitude_m", "crop",
        "record_count", "avg_quality", "last_seen",
    ] if c in stations.columns]
    df_show = stations[show_cols].copy()
    if "avg_quality" in df_show.columns:
        df_show["avg_quality"] = df_show["avg_quality"].round(3)
    if "altitude_m" in df_show.columns:
        df_show["altitude_m"] = df_show["altitude_m"].astype(int)
    st.dataframe(df_show, use_container_width=True, hide_index=True)

# ========================== SOURCES ==========================
with tab_sources:
    st.markdown('<div class="section-header">Data Source Distribution</div>',
                unsafe_allow_html=True)
    st.caption("Where each station's readings come from: IMD JSON API, imdlib gridded backup, or synthetic fallback")

    src_dist = load_data_source_distribution()
    if src_dist.empty:
        st.info("No telemetry data yet. Run the pipeline first.")
    else:
        # Source distribution bar
        st.bar_chart(src_dist.set_index("source")["count"])

        # Per-station breakdown
        st.markdown('<div class="section-header">Per-Station Sources</div>',
                    unsafe_allow_html=True)
        per_station = load_per_station_source()
        if not per_station.empty:
            station_names = get_station_name_map()
            per_station["name"] = per_station["station_id"].map(station_names)
            show = [c for c in ["station_id", "name", "source", "readings", "last_reading"]
                    if c in per_station.columns]
            st.dataframe(per_station[show], use_container_width=True, hide_index=True)

        # Source explanation
        st.markdown("""
        <div style="background:#fff;border:1px solid #e0dcd5;border-radius:8px;padding:16px;margin-top:16px;">
            <div style="font-weight:600;color:#1a1a1a;margin-bottom:8px;">Data Source Chain</div>
            <div style="font-size:0.85rem;color:#555;line-height:1.8;">
                <strong>IMD API</strong> — Real-time station data from city.imd.gov.in JSON endpoint (today's max/min temp, humidity, rainfall)<br/>
                <strong>imdlib</strong> — IMD gridded data at 0.25-0.5 degree resolution (T-1 day lag, temperature + rainfall only)<br/>
                <strong>synthetic</strong> — Generated fallback with configurable fault injection (used when both real sources fail, or with <code>--source synthetic</code>)
            </div>
        </div>
        """, unsafe_allow_html=True)

# ========================== HEALING ==========================
with tab_healing:
    df_raw = load_raw_telemetry(limit=500)
    df_clean = load_clean_telemetry(limit=500)

    if df_raw.empty and df_clean.empty:
        st.info("No telemetry data yet. Run the pipeline first.")
    else:
        # Metrics row
        col1, col2, col3, col4 = st.columns(4)
        raw_count = len(df_raw) if not df_raw.empty else 0
        clean_count = len(df_clean) if not df_clean.empty else 0
        col1.metric("Raw Records", raw_count)
        col2.metric("Clean Records", clean_count)

        healed = 0
        if not df_clean.empty and "heal_action" in df_clean.columns:
            healed = (df_clean["heal_action"] != "none").sum()
        col3.metric("Healed Records", healed)
        avg_q = df_clean["quality_score"].mean() if not df_clean.empty and "quality_score" in df_clean.columns else 0
        col4.metric("Avg Quality Score", f"{avg_q:.2f}")

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

        # Before / After comparison
        left, right = st.columns(2)
        with left:
            st.markdown("**Raw telemetry (before healing)**")
            if not df_raw.empty:
                show = [c for c in ["station_id", "ts", "temperature", "humidity",
                                     "wind_speed", "rainfall", "source"]
                        if c in df_raw.columns]
                st.dataframe(df_raw[show].head(50), use_container_width=True,
                             height=300, hide_index=True)
        with right:
            st.markdown("**Clean telemetry (after healing)**")
            if not df_clean.empty:
                show = [c for c in ["station_id", "ts", "temperature", "humidity",
                                     "wind_speed", "rainfall", "quality_score", "heal_action"]
                        if c in df_clean.columns]

                def _highlight_healed(col):
                    if col.name == "heal_action":
                        return ["background-color: rgba(42,157,143,0.15)"
                                if v and v != "none" else "" for v in col]
                    return [""] * len(col)

                df_disp = df_clean[show].head(50)
                if "heal_action" in df_disp.columns:
                    st.dataframe(df_disp.style.apply(_highlight_healed),
                                 use_container_width=True, height=300, hide_index=True)
                else:
                    st.dataframe(df_disp, use_container_width=True,
                                 height=300, hide_index=True)

        # Healing breakdown
        if not df_clean.empty and "heal_action" in df_clean.columns:
            st.markdown('<div class="section-header">Healing Breakdown</div>',
                        unsafe_allow_html=True)
            st.bar_chart(df_clean["heal_action"].value_counts())

        # Quality score distribution
        if not df_clean.empty and "quality_score" in df_clean.columns:
            st.markdown('<div class="section-header">Quality Score Distribution</div>',
                        unsafe_allow_html=True)
            st.bar_chart(df_clean["quality_score"].round(1).value_counts().sort_index())

        # Heal action legend
        st.markdown('<div class="section-header">Healing Actions Reference</div>',
                    unsafe_allow_html=True)
        legend_items = [
            ("cross_validated", "Reading matches Tomorrow.io reference — no correction needed"),
            ("null_filled", "Missing fields (wind, pressure) filled from Tomorrow.io"),
            ("anomaly_flagged", "Reading diverges from reference beyond threshold — flagged, not corrected"),
            ("null_filled+anomaly_flagged", "Both null-fill and anomaly flagging applied"),
            ("typo_corrected", "Decimal-place error detected and corrected (e.g. 320°C → 32.0°C)"),
            ("imputed_from_reference", "Station offline — entire reading imputed from reference source"),
            ("none", "No healing needed — reading passed all checks (synthetic mode only)"),
        ]
        for action, desc in legend_items:
            st.markdown(
                f'<div style="margin-bottom:6px;font-size:0.85rem;">'
                f'<code style="background:#f0ede8;padding:2px 6px;border-radius:3px;">{action}</code> '
                f'<span style="color:#555;">— {desc}</span></div>',
                unsafe_allow_html=True,
            )

# ========================== STATION HEALTH ==========================
with tab_health:
    if health.empty:
        st.info("No health data yet. Run the pipeline first.")
    else:
        col1, col2, col3, col4 = st.columns(4)
        total = len(stations)
        active = (stations["record_count"] > 0).sum()
        low_qual = ((stations["avg_quality"] < 0.7) & (stations["record_count"] > 0)).sum()
        no_data = (stations["record_count"] == 0).sum()
        col1.metric("Total Stations", total)
        col2.metric("Active", int(active))
        col3.metric("Low Quality", int(low_qual))
        col4.metric("No Data", int(no_data))

        display_cols = [c for c in [
            "station_id", "name", "state", "record_count", "avg_quality",
            "healed_count", "last_seen"
        ] if c in stations.columns]
        df_health = stations[display_cols].copy()

        def _quality_style(val):
            if not isinstance(val, float):
                return ""
            if val >= 0.85:
                return "background-color: rgba(42,157,143,0.15); color: #2a9d8f"
            elif val >= 0.7:
                return "background-color: rgba(212,160,25,0.15); color: #b87a1e"
            return "background-color: rgba(230,57,70,0.12); color: #e63946"

        if "avg_quality" in df_health.columns:
            df_health["avg_quality"] = df_health["avg_quality"].round(3)
            styled = df_health.style.map(_quality_style, subset=["avg_quality"])
            st.dataframe(styled, use_container_width=True, hide_index=True)
        else:
            st.dataframe(df_health, use_container_width=True, hide_index=True)

        if "avg_quality" in stations.columns:
            st.markdown('<div class="section-header">Average Quality by Station</div>',
                        unsafe_allow_html=True)
            chart_df = stations.set_index("station_id")[["avg_quality"]]
            if not chart_df.empty:
                st.bar_chart(chart_df)

# Chat toggle
from streamlit_app.chat_widget import render_chat_toggle
render_chat_toggle()
