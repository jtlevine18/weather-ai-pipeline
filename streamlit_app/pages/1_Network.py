"""Station Network page — map, health status, data quality."""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import streamlit as st
import pandas as pd

from streamlit_app.style import inject_css
from streamlit_app.data_helpers import (
    get_station_coords, load_station_health,
    load_raw_telemetry, load_clean_telemetry,
)

st.set_page_config(page_title="Station Network", page_icon="🗺️", layout="wide")
inject_css()

st.title("🗺️ Station Network")
st.caption("20 ground stations across Kerala and Tamil Nadu")

stations = get_station_coords()
health   = load_station_health()

# Merge health data
if not health.empty and "station_id" in health.columns:
    stations = stations.merge(health, on="station_id", how="left")
    stations["record_count"] = stations["record_count"].fillna(0).astype(int)
    stations["avg_quality"]  = stations["avg_quality"].fillna(0.0)
else:
    stations["record_count"] = 0
    stations["avg_quality"]  = 0.0

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_map, tab_health, tab_quality = st.tabs(["Map", "Health", "Data Quality"])

# ========================== MAP ==========================
with tab_map:
    # Color by health: green=ok, orange=low quality, red=no data
    def _color(row):
        if row["record_count"] == 0:
            return [200, 50, 50, 200]
        elif row.get("avg_quality", 1.0) < 0.7:
            return [255, 165, 0, 200]
        return [50, 200, 50, 200]

    map_df = stations.copy()
    map_df["color"]  = map_df.apply(_color, axis=1)
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
        # Use CARTO Positron (free, no Mapbox token required)
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

    # Station table
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

# ========================== HEALTH ==========================
with tab_health:
    if health.empty:
        st.info("No health data yet. Run `python run_pipeline.py` first.")
    else:
        col1, col2, col3, col4 = st.columns(4)
        total    = len(stations)
        active   = (stations["record_count"] > 0).sum() if "record_count" in stations.columns else 0
        low_qual = ((stations["avg_quality"] < 0.7) & (stations["record_count"] > 0)).sum() if "avg_quality" in stations.columns else 0
        no_data  = (stations["record_count"] == 0).sum() if "record_count" in stations.columns else 0
        col1.metric("Total Stations", total)
        col2.metric("Active", int(active))
        col3.metric("Low Quality", int(low_qual))
        col4.metric("No Data", int(no_data))

        # Color-coded health table
        display_cols = [c for c in [
            "station_id", "name", "state", "record_count", "avg_quality", "healed_count", "last_seen"
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

        if not health.empty and "avg_quality" in health.columns:
            st.markdown('<div class="section-header">Average Data Quality by Station</div>', unsafe_allow_html=True)
            chart_df = stations.set_index("station_id")[["avg_quality"]] if "avg_quality" in stations.columns else pd.DataFrame()
            if not chart_df.empty:
                st.bar_chart(chart_df)

# ========================== DATA QUALITY ==========================
with tab_quality:
    df_raw   = load_raw_telemetry(limit=500)
    df_clean = load_clean_telemetry(limit=500)

    if df_raw.empty and df_clean.empty:
        st.info("No telemetry data yet. Run the pipeline first.")
    else:
        col1, col2, col3, col4 = st.columns(4)
        raw_count   = len(df_raw) if not df_raw.empty else 0
        clean_count = len(df_clean) if not df_clean.empty else 0
        col1.metric("Raw Records", raw_count)
        col2.metric("Clean Records", clean_count)

        healed = 0
        if not df_clean.empty and "heal_action" in df_clean.columns:
            healed = (df_clean["heal_action"] != "none").sum()
        col3.metric("Healed Records", healed)
        heal_rate = f"{healed/max(1,clean_count):.0%}"
        col4.metric("Healing Rate", heal_rate)

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        left, right = st.columns(2)
        with left:
            st.markdown("**Raw telemetry (before healing)**")
            if not df_raw.empty:
                show = [c for c in ["station_id", "ts", "temperature", "humidity",
                                     "wind_speed", "rainfall", "quality_score"]
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

        if not df_clean.empty and "heal_action" in df_clean.columns:
            st.markdown('<div class="section-header">Healing Breakdown</div>', unsafe_allow_html=True)
            st.bar_chart(df_clean["heal_action"].value_counts())
