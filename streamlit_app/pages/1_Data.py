"""Data page — station weather readings, quality, and healing."""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import streamlit as st
import pandas as pd
import json

from streamlit_app.style import inject_css, inject_sidebar_nav
from streamlit_app.data_helpers import (
    get_station_coords, get_station_name_map, load_station_health,
    load_raw_telemetry, load_clean_telemetry,
    load_data_source_distribution, load_per_station_source,
    load_healing_log, load_healing_stats,
)

st.set_page_config(page_title="Data", page_icon="D", layout="wide")
inject_css()
inject_sidebar_nav()

st.title("Data")
st.caption("Weather station readings across Kerala and Tamil Nadu — raw ingestion, quality scores, and healing")

stations = get_station_coords()
health = load_station_health()
station_names = get_station_name_map()

# Merge health data
if not health.empty and "station_id" in health.columns:
    stations = stations.merge(health, on="station_id", how="left")
    stations["record_count"] = stations["record_count"].fillna(0).astype(int)
    stations["avg_quality"] = stations["avg_quality"].fillna(0.0)
else:
    stations["record_count"] = 0
    stations["avg_quality"] = 0.0

# Load telemetry
df_raw = load_raw_telemetry(limit=500)
df_clean = load_clean_telemetry(limit=500)

# ---------------------------------------------------------------------------
# Top metrics
# ---------------------------------------------------------------------------
total = len(stations)
active = int((stations["record_count"] > 0).sum())
avg_q = stations.loc[stations["record_count"] > 0, "avg_quality"].mean() if active > 0 else 0
raw_count = len(df_raw)
clean_count = len(df_clean)

mc1, mc2, mc3, mc4 = st.columns(4)
mc1.metric("Active Stations", f"{active}/{total}")
mc2.metric("Avg Quality", f"{avg_q:.0%}")
mc3.metric("Raw Readings", raw_count)
mc4.metric("Healed Readings", clean_count)

st.divider()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
SOURCE_STYLE = {
    "imd_api":    ("India Met Dept",       "#2E7D32"),
    "imdlib":     ("IMD Gridded Archive",  "#1565C0"),
    "synthetic":  ("Synthetic",            "#888"),
}

HEAL_STYLE = {
    "cross_validated":       ("Validated",  "#2a9d8f"),
    "null_filled":           ("Filled",     "#d4a019"),
    "ai_validated":          ("AI OK",      "#2a9d8f"),
    "ai_corrected":          ("AI Fixed",   "#4361ee"),
    "ai_filled":             ("AI Filled",  "#d4a019"),
    "ai_flagged":            ("AI Flagged", "#e76f51"),
    "anomaly_flagged":       ("Anomaly",    "#e63946"),
    "typo_corrected":        ("Typo Fix",   "#4361ee"),
    "imputed_from_reference":("Imputed",    "#e76f51"),
    "none":                  ("Original",   "#888"),
}


def _source_badge(src: str) -> str:
    label, color = SOURCE_STYLE.get(src or "", (src or "—", "#888"))
    return (
        f'<span style="background:{color}18;color:{color};border:1px solid {color}44;'
        f'padding:2px 8px;border-radius:4px;font-size:0.76rem;font-weight:600;">'
        f'{label}</span>'
    )


def _quality_badge(q) -> str:
    if q is None or (hasattr(q, '__class__') and str(q) == 'nan'):
        return "—"
    pct = int(float(q) * 100)
    color = "#2a9d8f" if pct >= 85 else "#d4a019" if pct >= 70 else "#e63946"
    return (
        f'<div style="display:inline-flex;align-items:center;gap:6px;">'
        f'<div style="background:#e0dcd5;border-radius:4px;height:8px;width:60px;">'
        f'<div style="background:{color};height:8px;border-radius:4px;width:{pct}%;"></div></div>'
        f'<span style="font-size:0.82rem;font-weight:600;color:{color};">{pct}%</span></div>'
    )


def _heal_badge(action: str) -> str:
    # Handle composite actions like "null_filled,cross_validated"
    if not action or action == "none":
        label, color = "Original", "#888"
    else:
        parts = [a.strip() for a in action.split(",") if a.strip()]
        badges = []
        for p in parts:
            l, c = HEAL_STYLE.get(p, (p, "#888"))
            badges.append(
                f'<span style="background:{c}18;color:{c};border:1px solid {c}44;'
                f'padding:1px 6px;border-radius:3px;font-size:0.72rem;font-weight:600;">{l}</span>'
            )
        return " ".join(badges)
    return (
        f'<span style="background:{color}18;color:{color};border:1px solid {color}44;'
        f'padding:1px 6px;border-radius:3px;font-size:0.72rem;font-weight:600;">{label}</span>'
    )


def _val(v, unit="", fmt=".1f") -> str:
    if v is None or (hasattr(v, '__class__') and str(v) == 'nan'):
        return '<span style="color:#ccc;">—</span>'
    return f'{v:{fmt}}{unit}'


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_stations, tab_healing, tab_map = st.tabs(["Station Readings", "Healing", "Map"])

# ========================== STATION READINGS ==========================
with tab_stations:
    # View toggle
    view_cols = st.columns([2, 2, 2, 6])
    with view_cols[0]:
        view_mode = st.radio("View", ["Clean (healed)", "Raw (original)"],
                             horizontal=True, label_visibility="collapsed")
    with view_cols[1]:
        state_opts = ["All States"] + sorted(stations["state"].dropna().unique().tolist())
        sel_state = st.selectbox("State", state_opts, key="data_state")

    is_raw = "Raw" in view_mode
    df = df_raw if is_raw else df_clean

    if df.empty:
        st.info("No telemetry data yet. Run the pipeline first.")
    else:
        # Add station names
        df = df.copy()
        df["station_name"] = df["station_id"].map(station_names).fillna(df["station_id"])
        df["state"] = df["station_id"].map(
            {row["station_id"]: row["state"] for _, row in stations.iterrows()}
        )

        # Filter
        if sel_state != "All States":
            df = df[df["state"] == sel_state]

        if df.empty:
            st.warning("No readings match the current filters.")
        else:
            # Latest reading per station
            latest = (
                df.sort_values("ts", ascending=False)
                .drop_duplicates(subset="station_id", keep="first")
                .sort_values(["state", "station_name"])
            )

            th = ("padding:10px 12px;text-align:left;font-size:0.76rem;"
                  "text-transform:uppercase;letter-spacing:1px;color:#666;")

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
                    humid = row.get("humidity")
                    wind = row.get("wind_speed")

                    # Color-code temperature
                    temp_color = "#1a1a1a"
                    if temp is not None:
                        try:
                            t = float(temp)
                            if t >= 40:   temp_color = "#C62828"
                            elif t >= 36: temp_color = "#E65100"
                            elif t <= 15: temp_color = "#0277BD"
                        except (ValueError, TypeError):
                            pass

                    rain_color = "#1a1a1a"
                    if rain is not None:
                        try:
                            r = float(rain)
                            if r >= 20:  rain_color = "#1565C0"
                            elif r >= 5: rain_color = "#1976D2"
                        except (ValueError, TypeError):
                            pass

                    # Source badge (raw has source column)
                    source_html = _source_badge(row.get("source", "")) if is_raw else ""

                    # Quality + heal action (clean only)
                    quality_html = ""
                    heal_html = ""
                    if not is_raw:
                        quality_html = _quality_badge(row.get("quality_score"))
                        heal_html = _heal_badge(str(row.get("heal_action", "none")))

                    ts_str = str(row.get("ts", ""))[:16]

                    rows_html += (
                        f'<tr style="border-bottom:1px solid #e0dcd5;">'
                        f'<td style="padding:10px 12px;font-weight:600;color:#1a1a1a;">'
                        f'{row["station_name"]}'
                        f'<div style="font-size:0.72rem;color:#999;font-weight:400;">{row["station_id"]}</div></td>'
                        f'<td style="padding:10px 12px;font-weight:600;color:{temp_color};font-variant-numeric:tabular-nums;">'
                        f'{_val(temp, " °C")}</td>'
                        f'<td style="padding:10px 12px;font-variant-numeric:tabular-nums;">{_val(humid, "%")}</td>'
                        f'<td style="padding:10px 12px;font-variant-numeric:tabular-nums;color:{rain_color};font-weight:600;">'
                        f'{_val(rain, " mm")}</td>'
                        f'<td style="padding:10px 12px;font-variant-numeric:tabular-nums;">{_val(wind, " m/s")}</td>'
                    )
                    if is_raw:
                        rows_html += f'<td style="padding:10px 12px;">{source_html}</td>'
                    else:
                        rows_html += (
                            f'<td style="padding:10px 8px;">{quality_html}</td>'
                            f'<td style="padding:10px 8px;">{heal_html}</td>'
                        )
                    rows_html += (
                        f'<td style="padding:10px 12px;color:#999;font-size:0.82rem;">{ts_str}</td>'
                        f'</tr>'
                    )

                # Build header based on mode
                if is_raw:
                    header = (
                        f'<th style="{th}">Station</th><th style="{th}">Temp</th>'
                        f'<th style="{th}">Humidity</th><th style="{th}">Rainfall</th>'
                        f'<th style="{th}">Wind</th><th style="{th}">Source</th>'
                        f'<th style="{th}">Time</th>'
                    )
                else:
                    header = (
                        f'<th style="{th}">Station</th><th style="{th}">Temp</th>'
                        f'<th style="{th}">Humidity</th><th style="{th}">Rainfall</th>'
                        f'<th style="{th}">Wind</th><th style="{th}">Quality</th>'
                        f'<th style="{th}">Healing</th><th style="{th}">Time</th>'
                    )

                st.html(
                    f'<table style="width:100%;border-collapse:collapse;background:#fff;'
                    f'border:1px solid #e0dcd5;border-radius:8px;overflow:hidden;margin-bottom:16px;">'
                    f'<thead><tr style="background:#f5f3ef;border-bottom:2px solid #e0dcd5;">'
                    f'{header}</tr></thead><tbody>{rows_html}</tbody></table>'
                )

            # Full data expander
            with st.expander("View all readings"):
                if is_raw:
                    show = [c for c in ["station_id", "ts", "temperature", "humidity",
                                        "wind_speed", "rainfall", "pressure", "source"]
                            if c in df.columns]
                else:
                    show = [c for c in ["station_id", "ts", "temperature", "humidity",
                                        "wind_speed", "rainfall", "pressure",
                                        "quality_score", "heal_action", "fields_filled"]
                            if c in df.columns]
                st.dataframe(
                    df[show].sort_values("ts", ascending=False),
                    width="stretch", height=400, hide_index=True,
                )

    # Data source info card
    st.markdown("""
    <div style="background:#fff;border:1px solid #e0dcd5;border-radius:8px;padding:16px;margin-top:16px;">
        <div style="font-weight:600;color:#1a1a1a;margin-bottom:8px;">Data Sources</div>
        <div style="font-size:0.85rem;color:#555;line-height:1.8;">
            <strong>India Meteorological Department</strong> — Real-time station data scraped from city.imd.gov.in (today's max/min temp, humidity, rainfall)<br/>
            <strong>IMD Gridded Archive</strong> — Historical gridded data at 0.25° resolution via imdlib (T-1 day lag, temperature + rainfall only)<br/>
            <strong>Tomorrow.io</strong> — Used for cross-validation and to fill fields IMD doesn't provide (wind speed, pressure, humidity)
        </div>
    </div>
    """, unsafe_allow_html=True)

# ========================== HEALING ==========================
with tab_healing:
    healing_log = load_healing_log(limit=200)
    healing_stats = load_healing_stats()
    has_ai_data = not healing_log.empty

    if df_raw.empty and df_clean.empty:
        st.info("No telemetry data yet. Run the pipeline first.")
    else:
        # AI agent status
        if has_ai_data and healing_stats.get("latest_run"):
            lr = healing_stats["latest_run"]
            sc1, sc2, sc3, sc4 = st.columns(4)
            sc1.metric("Model", lr.get("model", "—"))
            tokens_in = lr.get("tokens_in") or 0
            tokens_out = lr.get("tokens_out") or 0
            sc2.metric("Tokens", f"{tokens_in + tokens_out:,}")
            sc3.metric("Latency", f"{lr.get('latency_s', 0):.1f}s")
            cost = (tokens_in * 3.0 / 1_000_000) + (tokens_out * 15.0 / 1_000_000)
            sc4.metric("Est. Cost", f"${cost:.3f}")

            if lr.get("fallback_used"):
                st.warning("Rule-based fallback was used (AI agent unavailable)")
        elif not has_ai_data:
            st.markdown(
                '<div style="background:#fff8e6;border:1px solid #e0dcd5;border-radius:8px;padding:12px;'
                'font-size:0.85rem;color:#8a6d00;margin-bottom:16px;">'
                'No AI healing data yet. Run the pipeline with an Anthropic API key to enable the Claude healing agent.'
                '</div>', unsafe_allow_html=True,
            )

        # Assessment distribution as badges
        if has_ai_data and healing_stats.get("assessment_distribution"):
            st.markdown(
                '<p style="font-size:0.8rem;font-weight:600;text-transform:uppercase;'
                'letter-spacing:1.5px;color:#666;border-bottom:2px solid #d4a019;'
                'padding-bottom:6px;display:inline-block;">Assessment Summary</p>',
                unsafe_allow_html=True,
            )

            assessment_colors = {
                "good": "#2a9d8f", "corrected": "#4361ee", "filled": "#d4a019",
                "flagged": "#e76f51", "dropped": "#e63946",
            }
            dist = healing_stats["assessment_distribution"]
            badge_html = '<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px;">'
            for atype in ["good", "corrected", "filled", "flagged", "dropped"]:
                info = dist.get(atype, {"count": 0, "avg_quality": None})
                cnt = info["count"]
                color = assessment_colors.get(atype, "#888")
                badge_html += (
                    f'<div style="background:{color}15;border:1px solid {color}40;border-radius:6px;'
                    f'padding:8px 14px;text-align:center;min-width:90px;">'
                    f'<div style="font-size:1.4rem;font-weight:700;color:{color};">{cnt}</div>'
                    f'<div style="font-size:0.72rem;text-transform:uppercase;letter-spacing:1px;color:{color}99;">'
                    f'{atype}</div></div>'
                )
            badge_html += '</div>'
            st.markdown(badge_html, unsafe_allow_html=True)

        # Heal action breakdown as a table (replaces ugly bar chart)
        if not df_clean.empty and "heal_action" in df_clean.columns:
            st.markdown(
                '<p style="font-size:0.8rem;font-weight:600;text-transform:uppercase;'
                'letter-spacing:1.5px;color:#666;border-bottom:2px solid #d4a019;'
                'padding-bottom:6px;display:inline-block;margin-top:16px;">Healing Actions</p>',
                unsafe_allow_html=True,
            )

            action_counts = df_clean["heal_action"].value_counts()
            total_actions = action_counts.sum()
            th = ("padding:10px 12px;text-align:left;font-size:0.76rem;"
                  "text-transform:uppercase;letter-spacing:1px;color:#666;")

            action_rows = ""
            for action_name, count in action_counts.items():
                pct = count / total_actions * 100
                # Parse composite actions for badge display
                badge = _heal_badge(str(action_name))
                bar_color = "#2a9d8f" if "validated" in str(action_name) else "#d4a019" if "filled" in str(action_name) else "#e63946" if "flagged" in str(action_name) or "anomaly" in str(action_name) else "#888"
                action_rows += (
                    f'<tr style="border-bottom:1px solid #e0dcd5;">'
                    f'<td style="padding:10px 12px;">{badge}</td>'
                    f'<td style="padding:10px 12px;font-weight:600;font-variant-numeric:tabular-nums;">{count}</td>'
                    f'<td style="padding:10px 12px;">'
                    f'<div style="display:flex;align-items:center;gap:8px;">'
                    f'<div style="background:#e0dcd5;border-radius:4px;height:8px;width:120px;">'
                    f'<div style="background:{bar_color};height:8px;border-radius:4px;width:{pct}%;"></div></div>'
                    f'<span style="font-size:0.82rem;color:#666;">{pct:.0f}%</span>'
                    f'</div></td>'
                    f'</tr>'
                )

            st.html(
                f'<table style="width:100%;border-collapse:collapse;background:#fff;'
                f'border:1px solid #e0dcd5;border-radius:8px;overflow:hidden;">'
                f'<thead><tr style="background:#f5f3ef;border-bottom:2px solid #e0dcd5;">'
                f'<th style="{th}">Action</th><th style="{th}">Count</th>'
                f'<th style="{th}">Distribution</th>'
                f'</tr></thead><tbody>{action_rows}</tbody></table>'
            )

        # Per-reading AI assessments (expandable)
        if has_ai_data:
            st.markdown(
                '<p style="font-size:0.8rem;font-weight:600;text-transform:uppercase;'
                'letter-spacing:1.5px;color:#666;border-bottom:2px solid #d4a019;'
                'padding-bottom:6px;display:inline-block;margin-top:24px;">Per-Reading Assessments</p>',
                unsafe_allow_html=True,
            )
            st.caption("Claude's reasoning for each station reading — click to expand")

            for _, row in healing_log.iterrows():
                sid = row.get("station_id", "")
                sname = station_names.get(sid, sid)
                assessment = row.get("assessment", "unknown")
                color = assessment_colors.get(assessment, "#888") if has_ai_data else "#888"
                quality = row.get("quality_score", 0)
                reasoning = row.get("reasoning", "")
                tools = row.get("tools_used", "")

                try:
                    corrections = json.loads(row.get("corrections", "{}") or "{}")
                except (json.JSONDecodeError, TypeError):
                    corrections = {}
                try:
                    originals = json.loads(row.get("original_values", "{}") or "{}")
                except (json.JSONDecodeError, TypeError):
                    originals = {}

                emoji = {'good': '🟢', 'corrected': '🔵', 'filled': '🟡',
                         'flagged': '🟠', 'dropped': '🔴'}.get(assessment, '⚪')

                with st.expander(
                    f"{sname} — {emoji} {assessment} (Q: {quality:.2f})",
                    expanded=assessment in ("corrected", "flagged", "dropped"),
                ):
                    st.markdown(
                        f'<div style="font-size:0.9rem;color:#333;line-height:1.6;margin-bottom:12px;">'
                        f'{reasoning}</div>', unsafe_allow_html=True,
                    )

                    if corrections:
                        ba_html = '<div style="display:flex;gap:24px;margin-bottom:8px;">'
                        for field_name, new_val in corrections.items():
                            old_val = originals.get(field_name, "—")
                            old_disp = f"{old_val:.1f}" if isinstance(old_val, (int, float)) and old_val is not None else str(old_val)
                            new_disp = f"{new_val:.1f}" if isinstance(new_val, (int, float)) and new_val is not None else str(new_val)
                            ba_html += (
                                f'<div style="background:#fff;border:1px solid #e0dcd5;border-radius:6px;padding:8px 12px;">'
                                f'<div style="font-size:0.72rem;text-transform:uppercase;color:#888;letter-spacing:1px;">{field_name}</div>'
                                f'<span style="color:#e63946;text-decoration:line-through;">{old_disp}</span>'
                                f' → <span style="color:#2a9d8f;font-weight:600;">{new_disp}</span></div>'
                            )
                        ba_html += '</div>'
                        st.markdown(ba_html, unsafe_allow_html=True)

                    if tools:
                        tool_list = [t.strip() for t in tools.split(",") if t.strip()]
                        pills = " ".join(
                            f'<span style="background:#f0ede8;border:1px solid #d0ccc5;border-radius:12px;'
                            f'padding:2px 10px;font-size:0.72rem;color:#666;">{t}</span>'
                            for t in tool_list
                        )
                        st.markdown(pills, unsafe_allow_html=True)

        # Healing legend
        with st.expander("Healing Actions Reference"):
            legend_items = [
                ("cross_validated", "Reading matches Tomorrow.io reference within thresholds"),
                ("null_filled", "Missing fields filled from Tomorrow.io (expected — IMD doesn't provide wind/pressure/humidity)"),
                ("ai_validated", "AI agent confirmed reading quality against reference and seasonal norms"),
                ("ai_corrected", "AI agent corrected a value (e.g. decimal typo) with contextual reasoning"),
                ("ai_filled", "AI agent filled missing fields from reference data"),
                ("ai_flagged", "AI agent flagged a suspicious reading it couldn't confidently correct"),
                ("anomaly_flagged", "Reading diverges beyond acceptable threshold from reference"),
                ("typo_corrected", "Decimal-place error corrected (e.g. 320°C → 32.0°C)"),
                ("imputed_from_reference", "Station offline — entire reading sourced from reference"),
            ]
            for action, desc in legend_items:
                is_ai = action.startswith("ai_")
                bg = "#e8f4fd" if is_ai else "#f0ede8"
                st.markdown(
                    f'<div style="margin-bottom:6px;font-size:0.85rem;">'
                    f'<code style="background:{bg};padding:2px 6px;border-radius:3px;">{action}</code> '
                    f'<span style="color:#555;">— {desc}</span></div>',
                    unsafe_allow_html=True,
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

    # Station summary table
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
    st.dataframe(df_show, width="stretch", hide_index=True)

# Chat toggle
from streamlit_app.chat_widget import render_chat_toggle
render_chat_toggle()
