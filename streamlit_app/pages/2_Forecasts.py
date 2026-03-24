"""Forecasts page — station forecasts, model performance."""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import json
import streamlit as st
import pandas as pd

from streamlit_app.style import inject_css, inject_sidebar_nav, CONDITION_EMOJI, CONDITION_COLOR
from streamlit_app.data_helpers import load_forecasts, get_station_coords

st.set_page_config(page_title="Forecasts", page_icon="F", layout="wide")
inject_css()
inject_sidebar_nav()

st.title("Forecasts")
st.caption("Station-level weather predictions, model performance, and spatial downscaling")

forecasts = load_forecasts(limit=500)
_coords   = get_station_coords()

STATION_META = {
    row["station_id"]: (row["name"], row["state"])
    for _, row in _coords.iterrows()
}

CONDITION_STYLE = {
    "heavy_rain":    ("Heavy Rain",    "#1565C0", "⛈️"),
    "moderate_rain": ("Moderate Rain", "#1976D2", "🌦️"),
    "heat_stress":   ("Heat Stress",   "#C62828", "🌡️"),
    "drought_risk":  ("Drought Risk",  "#E65100", "🌵"),
    "frost_risk":    ("Frost Risk",    "#0277BD", "❄️"),
    "high_wind":     ("High Wind",     "#455A64", "💨"),
    "foggy":         ("Foggy",         "#546E7A", "🌫️"),
    "clear":         ("Clear",         "#2E7D32", "☀️"),
}

MODEL_LABELS = {
    "hybrid_mos":  ("Hybrid MOS",  "NWP + XGBoost correction", "#2a9d8f"),
    "persistence": ("Persistence", "Diurnal-adjusted fallback", "#e63946"),
}


def _condition_badge(cond: str) -> str:
    label, color, icon = CONDITION_STYLE.get(cond or "", (cond or "—", "#888", ""))
    return (
        f'<span style="background:{color};color:#fff;padding:3px 10px;'
        f'border-radius:12px;font-size:0.82rem;font-weight:600;">'
        f'{icon} {label}</span>'
    )


def _confidence_bar(conf) -> str:
    if conf is None or (hasattr(conf, '__class__') and str(conf) == 'nan'):
        return "—"
    pct = max(0, min(100, int(float(conf) * 100)))
    color = "#2a9d8f" if pct >= 70 else "#d4a019" if pct >= 40 else "#e63946"
    return (
        f'<div style="background:#e0dcd5;border-radius:4px;height:8px;'
        f'width:80px;display:inline-block;vertical-align:middle;">'
        f'<div style="background:{color};height:8px;border-radius:4px;width:{pct}%;"></div>'
        f'</div> <span style="font-size:0.82rem;color:#666;">{pct}%</span>'
    )


def _model_badge(model: str) -> str:
    label, _, color = MODEL_LABELS.get(model or "", (model or "—", "", "#888"))
    return (
        f'<span style="background:{color}22;color:{color};border:1px solid {color};'
        f'padding:2px 8px;border-radius:4px;font-size:0.78rem;font-weight:600;">'
        f'{label}</span>'
    )


if forecasts.empty:
    st.info("No forecast data yet. Run `python run_pipeline.py` to generate forecasts.")
    st.stop()

df = forecasts.copy()
df["station_name"] = df["station_id"].apply(lambda s: STATION_META.get(s, (s, "Unknown"))[0])
df["state"]        = df["station_id"].apply(lambda s: STATION_META.get(s, ("", "Unknown"))[1])

# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Stations Reporting", df["station_id"].nunique())
with col2:
    st.metric("Total Forecasts", len(df))
with col3:
    if "confidence" in df.columns:
        st.metric("Avg Confidence", f"{df['confidence'].mean():.0%}")
    else:
        st.metric("Avg Confidence", "—")
with col4:
    if "model_used" in df.columns:
        mos = (df["model_used"] == "hybrid_mos").sum()
        st.metric("MOS Model", f"{mos} ({100*mos//max(1,len(df))}%)")

st.divider()

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_fc, tab_model, tab_downscale = st.tabs(["Station Forecasts", "Model Performance", "Downscaling"])

# ========================== STATION FORECASTS ==========================
with tab_fc:
    filter_cols = st.columns([2, 2, 2])
    with filter_cols[0]:
        state_opts = ["All"] + sorted(df["state"].dropna().unique().tolist())
        sel_state = st.selectbox("State", state_opts, key="fc_state")
    with filter_cols[1]:
        cond_opts = ["All"] + sorted(df["condition"].dropna().unique().tolist()) if "condition" in df.columns else ["All"]
        sel_cond = st.selectbox("Condition", cond_opts, key="fc_cond")
    with filter_cols[2]:
        model_opts = ["All"] + sorted(df["model_used"].dropna().unique().tolist()) if "model_used" in df.columns else ["All"]
        sel_model = st.selectbox("Model", model_opts, key="fc_model")

    filtered = df.copy()
    if sel_state != "All":
        filtered = filtered[filtered["state"] == sel_state]
    if sel_cond != "All" and "condition" in filtered.columns:
        filtered = filtered[filtered["condition"] == sel_cond]
    if sel_model != "All" and "model_used" in filtered.columns:
        filtered = filtered[filtered["model_used"] == sel_model]

    if filtered.empty:
        st.warning("No forecasts match the current filters.")
    else:
        latest = (
            filtered
            .sort_values("issued_at", ascending=False)
            .drop_duplicates(subset="station_id", keep="first")
            .sort_values(["state", "station_name"])
        )

        th = "padding:10px 12px;text-align:left;font-size:0.78rem;text-transform:uppercase;letter-spacing:1px;color:#666;"

        for state_name, group in latest.groupby("state", sort=True):
            st.markdown(
                f'<p style="font-size:0.8rem;font-weight:600;text-transform:uppercase;'
                f'letter-spacing:1.5px;color:#666;border-bottom:2px solid #d4a019;'
                f'padding-bottom:6px;margin-top:24px;display:inline-block;">'
                f'{state_name}</p>',
                unsafe_allow_html=True,
            )

            rows_html = ""
            for _, row in group.iterrows():
                temp = row.get("temperature")
                rain = row.get("rainfall")
                temp_str = f"{temp:.1f} °C" if temp is not None else "—"
                rain_str = f"{rain:.1f} mm" if rain is not None else "—"

                temp_color = "#1a1a1a"
                if temp is not None:
                    if temp >= 40:   temp_color = "#C62828"
                    elif temp >= 36: temp_color = "#E65100"
                    elif temp <= 15: temp_color = "#0277BD"

                rain_color = "#1a1a1a"
                if rain is not None:
                    if rain >= 20:  rain_color = "#1565C0"
                    elif rain >= 5: rain_color = "#1976D2"

                cond_html  = _condition_badge(row.get("condition", ""))
                conf_html  = _confidence_bar(row.get("confidence"))
                model_html = _model_badge(row.get("model_used", ""))

                rows_html += (
                    f'<tr style="border-bottom:1px solid #e0dcd5;">'
                    f'<td style="padding:10px 12px;font-weight:600;color:#1a1a1a;">{row["station_name"]}</td>'
                    f'<td style="padding:10px 12px;font-weight:600;color:{temp_color};font-variant-numeric:tabular-nums;">{temp_str}</td>'
                    f'<td style="padding:10px 12px;font-weight:600;color:{rain_color};font-variant-numeric:tabular-nums;">{rain_str}</td>'
                    f'<td style="padding:10px 12px;">{cond_html}</td>'
                    f'<td style="padding:10px 12px;">{model_html}</td>'
                    f'<td style="padding:10px 8px;">{conf_html}</td>'
                    f'</tr>'
                )

            st.html(
                f'<table style="width:100%;border-collapse:collapse;background:#fff;'
                f'border:1px solid #e0dcd5;border-radius:8px;overflow:hidden;margin-bottom:16px;">'
                f'<thead><tr style="background:#f5f3ef;border-bottom:2px solid #e0dcd5;">'
                f'<th style="{th}">Station</th><th style="{th}">Temp</th>'
                f'<th style="{th}">Rainfall</th><th style="{th}">Condition</th>'
                f'<th style="{th}">Model</th><th style="{th}">Confidence</th>'
                f'</tr></thead><tbody>{rows_html}</tbody></table>'
            )

        with st.expander("View all forecast records"):
            show_cols = [c for c in [
                "station_name", "state", "temperature", "humidity", "wind_speed",
                "rainfall", "condition", "model_used", "confidence", "issued_at",
            ] if c in filtered.columns]
            st.dataframe(
                filtered[show_cols].sort_values("issued_at", ascending=False),
                width="stretch",
                height=400,
                hide_index=True,
            )

# ========================== MODEL PERFORMANCE ==========================
with tab_model:
    st.markdown(
        '<p style="font-size:0.8rem;font-weight:600;text-transform:uppercase;'
        'letter-spacing:1.5px;color:#666;border-bottom:2px solid #d4a019;'
        'padding-bottom:6px;display:inline-block;">Degradation Chain</p>',
        unsafe_allow_html=True,
    )

    tier_cols = st.columns(2)
    tier_data = [
        ("1", "Hybrid MOS",  "NWP + XGBoost correction",
         "Open-Meteo NWP baseline with local XGBoost MOS correction (12-feature vector)", "#2a9d8f"),
        ("2", "Persistence", "Diurnal-adjusted fallback",
         "Last observation carried forward with time-of-day adjustment when NWP unavailable", "#e63946"),
    ]
    for col, (tier, name, subtitle, desc, color) in zip(tier_cols, tier_data):
        with col:
            st.markdown(
                f'<div style="background:#fff;border:1px solid #e0dcd5;border-left:4px solid {color};'
                f'border-radius:8px;padding:16px;min-height:130px;">'
                f'<span style="font-size:0.72rem;color:#999;text-transform:uppercase;letter-spacing:1px;">Tier {tier}</span>'
                f'<p style="font-weight:700;color:#1a1a1a;margin:4px 0 2px;font-size:1rem;">{name}</p>'
                f'<p style="font-size:0.78rem;color:#888;margin:0 0 8px;">{subtitle}</p>'
                f'<p style="font-size:0.82rem;color:#555;margin:0;">{desc}</p>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)

    if "model_used" in df.columns:
        st.markdown(
            '<p style="font-size:0.8rem;font-weight:600;text-transform:uppercase;'
            'letter-spacing:1.5px;color:#666;border-bottom:2px solid #d4a019;'
            'padding-bottom:6px;display:inline-block;">Usage Breakdown</p>',
            unsafe_allow_html=True,
        )
        model_counts = df["model_used"].value_counts()
        total = len(df)
        usage_cols = st.columns(min(len(model_counts), 4))
        for i, (mname, count) in enumerate(model_counts.items()):
            _, _, color = MODEL_LABELS.get(mname, (mname, "", "#888"))
            pct = count / total * 100
            with usage_cols[i % len(usage_cols)]:
                st.markdown(
                    f'<div style="background:#fff;border:1px solid #e0dcd5;border-radius:8px;padding:16px;text-align:center;">'
                    f'<p style="font-size:2rem;font-weight:700;color:{color};margin:0;">{pct:.0f}%</p>'
                    f'<p style="font-size:0.82rem;color:#666;margin:4px 0 0;">{mname}</p>'
                    f'<p style="font-size:0.78rem;color:#999;margin:2px 0 0;">{count} forecasts</p>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    if "confidence" in df.columns and "model_used" in df.columns:
        st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)
        st.markdown(
            '<p style="font-size:0.8rem;font-weight:600;text-transform:uppercase;'
            'letter-spacing:1.5px;color:#666;border-bottom:2px solid #d4a019;'
            'padding-bottom:6px;display:inline-block;">Confidence by Model</p>',
            unsafe_allow_html=True,
        )
        conf_stats = (
            df.groupby("model_used")["confidence"]
            .agg(["mean", "min", "max", "count"])
            .sort_values("mean", ascending=False)
        )
        th = "padding:10px 12px;text-align:left;font-size:0.78rem;text-transform:uppercase;letter-spacing:1px;color:#666;"
        conf_rows = ""
        for mname, row in conf_stats.iterrows():
            _, _, color = MODEL_LABELS.get(mname, (mname, "", "#888"))
            bar_w = int(row["mean"] * 100)
            conf_rows += (
                f'<tr style="border-bottom:1px solid #e0dcd5;">'
                f'<td style="padding:10px 12px;font-weight:600;">{mname}</td>'
                f'<td style="padding:10px 12px;">'
                f'<div style="display:flex;align-items:center;gap:8px;">'
                f'<div style="background:#e0dcd5;border-radius:4px;height:10px;width:120px;">'
                f'<div style="background:{color};height:10px;border-radius:4px;width:{bar_w}%;"></div></div>'
                f'<span style="font-weight:600;font-size:0.88rem;">{row["mean"]:.0%}</span>'
                f'</div></td>'
                f'<td style="padding:10px 12px;color:#999;font-size:0.82rem;">{row["min"]:.0%}</td>'
                f'<td style="padding:10px 12px;color:#999;font-size:0.82rem;">{row["max"]:.0%}</td>'
                f'<td style="padding:10px 12px;color:#999;font-size:0.82rem;">{int(row["count"])}</td>'
                f'</tr>'
            )
        st.html(
            f'<table style="width:100%;border-collapse:collapse;background:#fff;'
            f'border:1px solid #e0dcd5;border-radius:8px;overflow:hidden;">'
            f'<thead><tr style="background:#f5f3ef;border-bottom:2px solid #e0dcd5;">'
            f'<th style="{th}">Model</th><th style="{th}">Avg Confidence</th>'
            f'<th style="{th}">Min</th><th style="{th}">Max</th><th style="{th}">Count</th>'
            f'</tr></thead><tbody>{conf_rows}</tbody></table>'
        )

    # ==================================================================
    # MOS Training Section
    # ==================================================================
    st.markdown("<div style='height:32px'></div>", unsafe_allow_html=True)
    st.markdown(
        '<p style="font-size:0.8rem;font-weight:600;text-transform:uppercase;'
        'letter-spacing:1.5px;color:#666;border-bottom:2px solid #d4a019;'
        'padding-bottom:6px;display:inline-block;">MOS Model Training</p>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<p style="font-size:0.85rem;color:#555;">'
        'Collect observation + NWP pairs by running Steps 1-3 (free APIs only — no Claude cost). '
        'Once you have enough data, retrain the XGBoost MOS model for better forecast accuracy.</p>',
        unsafe_allow_html=True,
    )

    # Show current training data stats
    try:
        import duckdb
        _db = os.path.join(os.path.dirname(__file__), "..", "..", "weather.duckdb")
        _conn = duckdb.connect(_db, read_only=True)
        _clean_n = _conn.execute("SELECT COUNT(*) FROM clean_telemetry").fetchone()[0]
        _fc_n = _conn.execute("SELECT COUNT(*) FROM forecasts").fetchone()[0]
        _stations_n = _conn.execute("SELECT COUNT(DISTINCT station_id) FROM forecasts").fetchone()[0]
        _conn.close()
    except Exception:
        _clean_n = _fc_n = _stations_n = 0

    m1, m2, m3 = st.columns(3)
    with m1:
        st.metric("Clean Observations", _clean_n)
    with m2:
        st.metric("Forecast Pairs", _fc_n)
    with m3:
        st.metric("Stations with Data", _stations_n)

    # Show existing model metrics if available
    _metrics_path = os.path.join(os.path.dirname(__file__), "..", "..", "metrics", "mos_metrics.json")
    if os.path.exists(_metrics_path):
        with open(_metrics_path) as _mf:
            _metrics = json.load(_mf)
        mm1, mm2, mm3, mm4 = st.columns(4)
        with mm1:
            st.metric("Model MAE", f"{_metrics.get('mae', '?')} °C")
        with mm2:
            st.metric("Model RMSE", f"{_metrics.get('rmse', '?')} °C")
        with mm3:
            st.metric("Model R²", f"{_metrics.get('r2', '?')}")
        with mm4:
            st.metric("Training Samples", _metrics.get("n_train", "?"))

# ========================== DOWNSCALING ==========================
with tab_downscale:
    st.markdown('<div class="section-header">Spatial Downscaling</div>',
                unsafe_allow_html=True)
    st.markdown(
        "Station forecasts are adjusted to individual farmer GPS coordinates using "
        "**Inverse Distance Weighting (IDW)** on a NASA POWER 5x5 grid, plus a "
        "**lapse-rate elevation correction** of 6.5 C per 1000m."
    )

    # Load farmer data for the map
    from streamlit_app.data_helpers import load_farmer_profiles
    farmers_df = load_farmer_profiles()

    if farmers_df.empty:
        st.info("No farmer data available. Run the pipeline to generate farmer profiles.")
    else:
        # Station + Farmer map
        try:
            import pydeck as pdk

            station_layer = pdk.Layer(
                "ScatterplotLayer",
                data=_coords.rename(columns={"lon": "longitude", "lat": "latitude"}),
                get_position=["longitude", "latitude"],
                get_color=[212, 160, 25, 220],
                get_radius=8000,
                pickable=True,
            )
            farmer_layer = pdk.Layer(
                "ScatterplotLayer",
                data=farmers_df.rename(columns={"gps_lon": "longitude", "gps_lat": "latitude"}).dropna(subset=["longitude", "latitude"]),
                get_position=["longitude", "latitude"],
                get_color=[42, 157, 143, 200],
                get_radius=4000,
                pickable=True,
            )
            view = pdk.ViewState(latitude=10.5, longitude=78.0, zoom=5.5)
            st.pydeck_chart(pdk.Deck(
                layers=[station_layer, farmer_layer],
                initial_view_state=view,
                map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
            ))
            st.markdown(
                '<div style="display:flex;gap:16px;margin-top:8px;font-size:0.8rem;color:#666;">'
                '<span><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#d4a019;margin-right:4px;"></span>Stations</span>'
                '<span><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#2a9d8f;margin-right:4px;"></span>Farmer locations</span>'
                '</div>',
                unsafe_allow_html=True,
            )
        except Exception:
            st.info("Map unavailable — pydeck not installed")

        # Before/After demo table
        st.markdown('<div class="section-header">Downscaling Effect</div>',
                    unsafe_allow_html=True)
        st.caption("Showing how station temperatures adjust for each farmer's specific location and elevation")

        rows = []
        for _, farmer in farmers_df.iterrows():
            sid = farmer.get("station_id")
            if not sid:
                continue
            station_info = _coords[_coords["station_id"] == sid]
            if station_info.empty:
                continue
            s = station_info.iloc[0]
            f_lat = farmer.get("gps_lat")
            f_lon = farmer.get("gps_lon")
            if f_lat is None or f_lon is None:
                continue

            # Get latest forecast temp for this station
            station_fc = df[df["station_id"] == sid].sort_values("issued_at", ascending=False)
            if station_fc.empty:
                continue
            fc_temp = station_fc.iloc[0].get("temperature")
            if fc_temp is None:
                continue

            # Estimate altitude delta (farmer near station, small offset)
            alt_delta = 0  # No farmer altitude in current data
            lapse_correction = round(-0.0065 * alt_delta, 2)

            rows.append({
                "Station": f"{s['name']} ({sid})",
                "Station Temp": f"{fc_temp:.1f} C",
                "Farmer": farmer.get("name", "?"),
                "Distance (km)": round(((f_lat - s["lat"])**2 + (f_lon - s["lon"])**2)**0.5 * 111, 1),
                "Lapse Delta": f"{lapse_correction:+.1f} C",
                "Final Temp": f"{fc_temp + lapse_correction:.1f} C",
            })

        if rows:
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

        # Lapse-rate explanation card
        st.markdown("""
        <div style="background:#fff;border:1px solid #e0dcd5;border-radius:8px;padding:16px;margin-top:12px;">
            <div style="font-weight:600;color:#1a1a1a;margin-bottom:6px;">Lapse-Rate Correction</div>
            <code style="font-size:0.9rem;color:#333;">Final = IDW_Temp - (0.0065 x altitude_delta_m)</code>
            <div style="color:#666;font-size:0.85rem;margin-top:6px;">
                Temperature drops approximately 6.5 C per 1000m elevation gain.
                The IDW interpolation uses inverse distance weighting (power=2) on a 5x5 NASA POWER grid
                (~0.5 degree radius) around the farmer's coordinates.
            </div>
        </div>
        """, unsafe_allow_html=True)

# Chat toggle
from streamlit_app.chat_widget import render_chat_toggle
render_chat_toggle()
