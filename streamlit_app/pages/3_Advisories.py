"""Advisories page — alert feed, SMS preview, condition distribution."""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import streamlit as st
import pandas as pd

from streamlit_app.style import inject_css, CONDITION_EMOJI, CONDITION_COLOR
from streamlit_app.data_helpers import load_alerts, load_delivery_log, get_station_coords

st.set_page_config(page_title="Advisories", page_icon="📢", layout="wide")
inject_css()

st.title("📢 Agricultural Advisories")

alerts   = load_alerts(limit=200)
delivery = load_delivery_log(limit=200)

# Station name lookup
_coords = get_station_coords()
STATION_NAMES = {row["station_id"]: row["name"] for _, row in _coords.iterrows()}

if alerts.empty:
    st.info("No advisories generated yet. Run `python run_pipeline.py` to generate data.")
    st.stop()

# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Total Advisories", len(alerts))
with col2:
    if "provider" in alerts.columns:
        rag = (alerts["provider"] == "rag_claude").sum()
        st.metric("RAG+Claude", rag)
with col3:
    if "language" in alerts.columns:
        ta = (alerts["language"] == "ta").sum()
        ml = (alerts["language"] == "ml").sum()
        st.metric("Tamil / Malayalam", f"{ta} / {ml}")
with col4:
    if not delivery.empty and "status" in delivery.columns:
        sent = (delivery["status"].isin(["sent", "dry_run"])).sum()
        st.metric("Deliveries", sent)

st.divider()

# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------
col1, col2, col3 = st.columns(3)
with col1:
    lang_filter = st.selectbox("Language", ["All", "ta", "ml", "en"])
with col2:
    cond_options = ["All"] + sorted(alerts["condition"].dropna().unique().tolist()) if "condition" in alerts.columns else ["All"]
    cond_filter  = st.selectbox("Condition", cond_options)
with col3:
    prov_options = ["All"] + sorted(alerts["provider"].dropna().unique().tolist()) if "provider" in alerts.columns else ["All"]
    prov_filter  = st.selectbox("Provider", prov_options)

filtered = alerts.copy()
if lang_filter != "All":
    filtered = filtered[filtered["language"] == lang_filter]
if cond_filter != "All" and "condition" in filtered.columns:
    filtered = filtered[filtered["condition"] == cond_filter]
if prov_filter != "All" and "provider" in filtered.columns:
    filtered = filtered[filtered["provider"] == prov_filter]

# ---------------------------------------------------------------------------
# Advisory feed
# ---------------------------------------------------------------------------

# Hover-to-show-English CSS
st.markdown("""
<style>
.advisory-card { position: relative; }
.advisory-card .en-overlay {
    display: none;
    position: absolute;
    top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(255,255,255,0.97);
    border-radius: 8px;
    padding: 10px 14px;
    z-index: 10;
    border: 2px solid #d4a019;
    box-shadow: 0 2px 12px rgba(0,0,0,0.10);
    flex-direction: column;
    justify-content: center;
}
.advisory-card:hover .en-overlay { display: flex; }
.en-overlay .en-label {
    font-size: 0.65rem; font-weight: 700;
    text-transform: uppercase; letter-spacing: 1px;
    color: #d4a019; margin-bottom: 5px;
}
.en-overlay .en-text { color: #1a1a1a; font-size: 0.88rem; line-height: 1.5; }
</style>
""", unsafe_allow_html=True)

st.markdown(
    f'<div class="section-header">Advisory Feed — {len(filtered)} results</div>',
    unsafe_allow_html=True,
)

for _, row in filtered.head(20).iterrows():
        cond     = row.get("condition", "clear")
        emoji    = CONDITION_EMOJI.get(cond, "🌤️")
        lang     = row.get("language", "en")
        provider = row.get("provider", "?")
        sid      = row.get("station_id", "?")
        name     = STATION_NAMES.get(sid, sid)

        advisory_en    = str(row.get("advisory_en", "") or "")
        advisory_local = str(row.get("advisory_local", "") or "")

        badge_color = CONDITION_COLOR.get(cond, "#555")
        prov_badge  = "🤖 RAG+Claude" if provider == "rag_claude" else "📋 Rule-based"
        border_color = badge_color

        has_en = bool(advisory_en and advisory_en != advisory_local)
        if has_en:
            en_safe = advisory_en[:200].replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
            overlay_html = (
                f'<div class="en-overlay">'
                f'<div class="en-label">🌐 English translation</div>'
                f'<div class="en-text">{en_safe}</div>'
                f'</div>'
            )
            hint = '<span style="color:#d4a019;font-size:0.7rem;margin-left:6px;">🌐 hover</span>'
        else:
            overlay_html = ""
            hint = ""

        display_text = advisory_local if advisory_local else advisory_en
        issued = str(row.get("issued_at", ""))[:16]

        st.markdown(
            f"<div class='advisory-card' style='border:1px solid #e0dcd5;"
            f"border-left:3px solid {border_color};"
            f"border-radius:8px;padding:10px 14px;margin-bottom:8px;background:#fff;'>"
            f"{overlay_html}"
            f"<div style='display:flex;align-items:center;gap:8px;margin-bottom:4px;'>"
            f"<span style='font-size:1.1rem'>{emoji}</span>"
            f"<strong style='color:#1a1a1a;'>{name}</strong>"
            f"<span style='color:#aaa;font-size:0.75rem'>{sid}</span>"
            f"<span style='background:{badge_color};color:white;padding:2px 8px;"
            f"border-radius:10px;font-size:0.7rem;font-weight:600'>"
            f"{cond.replace('_',' ').title()}</span>"
            f"<span style='margin-left:auto;color:#888;font-size:0.7rem'>"
            f"{prov_badge} · {lang}</span>"
            f"{hint}"
            f"</div>"
            f"<div style='color:#555;font-size:0.85rem;line-height:1.5;margin:4px 0'>"
            f"{display_text[:200]}{'…' if len(display_text) > 200 else ''}"
            f"</div>"
            f"<div style='color:#aaa;font-size:0.72rem;margin-top:2px'>{issued}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

# ---------------------------------------------------------------------------
# SMS preview
# ---------------------------------------------------------------------------
st.divider()
st.markdown('<div class="section-header">SMS Preview (160-char format)</div>', unsafe_allow_html=True)

if not alerts.empty:
    for _, row in alerts.head(3).iterrows():
        cond     = (row.get("condition") or "clear").replace("_", " ").upper()
        temp     = row.get("temperature")
        rain     = row.get("rainfall")
        advisory = str(row.get("advisory_local") or row.get("advisory_en", ""))
        sid      = row.get("station_id", "?")
        name     = STATION_NAMES.get(sid, sid)
        header   = f"[WEATHER] {name.upper()} {cond}"
        if temp is not None:
            header += f" {temp:.0f}C"
        if rain is not None and rain > 0:
            header += f" {rain:.0f}mm"
        sms = f"{header}\n{advisory}"
        if len(sms) > 160:
            sms = sms[:157] + "..."
        st.code(sms, language=None)
