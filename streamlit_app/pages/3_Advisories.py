"""Advisories page — advisory feed, forecast lineage, farmer/DPI context, delivery."""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import streamlit as st
import pandas as pd

from streamlit_app.style import inject_css, CONDITION_EMOJI, CONDITION_COLOR
from streamlit_app.data_helpers import (
    load_alerts, load_delivery_log, get_station_name_map,
    load_advisory_lineage, load_farmer_profiles, load_farmer_profile_detail,
)

st.set_page_config(page_title="Advisories", page_icon="A", layout="wide")
inject_css()

st.title("Advisories")
st.caption("Translation, delivery, and farmer context")

alerts = load_alerts(limit=200)
delivery = load_delivery_log(limit=200)

STATION_NAMES = get_station_name_map()

if alerts.empty:
    st.info("No advisories generated yet. Run the pipeline to generate data.")
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
        sent = delivery["status"].isin(["sent", "dry_run"]).sum()
        st.metric("Deliveries", sent)

st.divider()

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_feed, tab_lineage, tab_farmers, tab_delivery = st.tabs(
    ["Advisory Feed", "Lineage", "Farmers & DPI", "Delivery"]
)

# ========================== ADVISORY FEED ==========================
with tab_feed:
    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        lang_filter = st.selectbox("Language", ["All", "ta", "ml", "en"])
    with col2:
        cond_options = ["All"] + sorted(alerts["condition"].dropna().unique().tolist()) if "condition" in alerts.columns else ["All"]
        cond_filter = st.selectbox("Condition", cond_options)
    with col3:
        prov_options = ["All"] + sorted(alerts["provider"].dropna().unique().tolist()) if "provider" in alerts.columns else ["All"]
        prov_filter = st.selectbox("Provider", prov_options)

    filtered = alerts.copy()
    if lang_filter != "All":
        filtered = filtered[filtered["language"] == lang_filter]
    if cond_filter != "All" and "condition" in filtered.columns:
        filtered = filtered[filtered["condition"] == cond_filter]
    if prov_filter != "All" and "provider" in filtered.columns:
        filtered = filtered[filtered["provider"] == prov_filter]

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
        cond = row.get("condition") or "clear"
        emoji = CONDITION_EMOJI.get(cond, "")
        lang = row.get("language", "en")
        provider = row.get("provider", "?")
        sid = row.get("station_id", "?")
        name = STATION_NAMES.get(sid, sid)

        advisory_en = str(row.get("advisory_en", "") or "")
        advisory_local = str(row.get("advisory_local", "") or "")

        badge_color = CONDITION_COLOR.get(cond, "#555")
        prov_badge = "RAG+Claude" if provider == "rag_claude" else "Rule-based"
        border_color = badge_color

        has_en = bool(advisory_en and advisory_en != advisory_local)
        if has_en:
            en_safe = advisory_en[:200].replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
            overlay_html = (
                f'<div class="en-overlay">'
                f'<div class="en-label">English translation</div>'
                f'<div class="en-text">{en_safe}</div>'
                f'</div>'
            )
            hint = '<span style="color:#d4a019;font-size:0.7rem;margin-left:6px;">hover for English</span>'
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
            f"{cond.replace('_', ' ').title()}</span>"
            f"<span style='margin-left:auto;color:#888;font-size:0.7rem'>"
            f"{prov_badge} · {lang}</span>"
            f"{hint}"
            f"</div>"
            f"<div style='color:#555;font-size:0.85rem;line-height:1.5;margin:4px 0'>"
            f"{display_text[:200]}{'...' if len(display_text) > 200 else ''}"
            f"</div>"
            f"<div style='color:#aaa;font-size:0.72rem;margin-top:2px'>{issued}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    # SMS preview
    st.markdown('<div class="section-header">SMS Preview (160-char format)</div>',
                unsafe_allow_html=True)
    for _, row in alerts.head(3).iterrows():
        cond = (row.get("condition") or "clear").replace("_", " ").upper()
        temp = row.get("temperature")
        rain = row.get("rainfall")
        advisory = str(row.get("advisory_local") or row.get("advisory_en", ""))
        sid = row.get("station_id", "?")
        name = STATION_NAMES.get(sid, sid)
        header = f"[WEATHER] {name.upper()} {cond}"
        if temp is not None:
            header += f" {temp:.0f}C"
        if rain is not None and rain > 0:
            header += f" {rain:.0f}mm"
        sms = f"{header}\n{advisory}"
        if len(sms) > 160:
            sms = sms[:157] + "..."
        st.code(sms, language=None)

# ========================== LINEAGE ==========================
with tab_lineage:
    st.markdown('<div class="section-header">Forecast to Advisory Lineage</div>',
                unsafe_allow_html=True)
    st.caption("How each weather forecast was transformed into an agricultural advisory")

    lineage = load_advisory_lineage(limit=30)

    if lineage.empty:
        st.info("No lineage data available. Run the pipeline to generate forecast-advisory pairs.")
    else:
        for _, row in lineage.iterrows():
            sid = row.get("station_id", "?")
            name = STATION_NAMES.get(sid, sid)

            fc_temp = row.get("fc_temperature")
            fc_rain = row.get("fc_rainfall")
            fc_cond = row.get("fc_condition") or "unknown"
            fc_model = row.get("fc_model") or "?"
            fc_conf = row.get("fc_confidence")

            alert_cond = row.get("alert_condition") or "?"
            provider = row.get("provider") or "?"
            lang = row.get("language") or "?"
            advisory_local = str(row.get("advisory_local", "") or "")
            advisory_en = str(row.get("advisory_en", "") or "")

            cond_color = CONDITION_COLOR.get(fc_cond, "#888")

            temp_str = f"{fc_temp:.1f} C" if fc_temp is not None else "--"
            rain_str = f"{fc_rain:.1f}mm" if fc_rain is not None else "--"
            conf_str = f"{fc_conf:.0%}" if fc_conf is not None else "--"
            adv_text = (advisory_local or advisory_en)[:150]

            left, arrow, right = st.columns([2, 0.3, 3])
            with left:
                st.markdown(f"""
                <div style="background:#fff;border:1px solid #e0dcd5;border-radius:8px;padding:12px;">
                    <div style="font-weight:600;color:#1a1a1a;">{name}</div>
                    <div style="font-size:0.82rem;color:#555;margin-top:4px;">
                        Temp: {temp_str} · Rain: {rain_str}<br/>
                        <span style="background:{cond_color};color:#fff;padding:1px 6px;border-radius:3px;
                                     font-size:0.7rem;">{fc_cond.replace('_',' ')}</span>
                        <span style="color:#888;font-size:0.75rem;margin-left:6px;">{fc_model} · {conf_str}</span>
                    </div>
                </div>""", unsafe_allow_html=True)
            with arrow:
                st.markdown('<div style="text-align:center;padding-top:20px;color:#d4a019;font-size:1.3rem;">&rarr;</div>',
                            unsafe_allow_html=True)
            with right:
                prov_label = "RAG+Claude" if provider == "rag_claude" else "Rule-based"
                st.markdown(f"""
                <div style="background:#fff;border:1px solid #e0dcd5;border-left:3px solid #d4a019;
                            border-radius:8px;padding:12px;">
                    <span style="font-size:0.72rem;color:#888;">{prov_label} · {lang}</span>
                    <div style="color:#555;font-size:0.82rem;line-height:1.4;margin-top:4px;">
                        {adv_text}...
                    </div>
                </div>""", unsafe_allow_html=True)

# ========================== FARMERS & DPI ==========================
with tab_farmers:
    st.markdown('<div class="section-header">Farmer Profiles & DPI Context</div>',
                unsafe_allow_html=True)
    st.caption("Digital Public Infrastructure data that shapes personalized advisories")

    farmers_df = load_farmer_profiles()

    if farmers_df.empty:
        st.info("No farmer data available. Run the pipeline first.")
    else:
        # Farmer selector
        farmer_labels = farmers_df.apply(
            lambda r: f"{r['name']} — {r['district']}, {r['station_id']}", axis=1
        ).tolist()
        selected = st.selectbox("Select farmer", farmer_labels)

        if selected:
            idx = farmer_labels.index(selected)
            farmer = farmers_df.iloc[idx]
            phone = farmer["phone"]
            detail = load_farmer_profile_detail(phone)

            if detail:
                left, right = st.columns(2)

                with left:
                    # Identity card
                    aa = detail["aadhaar"]
                    st.markdown(f"""
                    <div style="background:#fff;border:1px solid #e0dcd5;border-radius:8px;padding:16px;">
                        <div style="font-weight:700;font-size:1.1rem;color:#1a1a1a;">{aa.name}</div>
                        <div style="color:#888;font-size:0.9rem;">{aa.name_local}</div>
                        <div style="margin-top:8px;font-size:0.85rem;color:#555;line-height:1.7;">
                            District: {aa.district}, {aa.state}<br/>
                            Language: {aa.language.upper()}<br/>
                            Crops: {', '.join(detail['primary_crops'])}<br/>
                            Total area: {detail['total_area']:.2f} ha
                        </div>
                    </div>""", unsafe_allow_html=True)

                    # Land record
                    if detail["land_records"]:
                        land = detail["land_records"][0]
                        st.markdown(f"""
                        <div style="background:#fff;border:1px solid #e0dcd5;border-radius:8px;padding:16px;margin-top:10px;">
                            <div style="font-weight:600;color:#666;font-size:0.75rem;text-transform:uppercase;letter-spacing:1px;">Land Record</div>
                            <div style="font-size:0.85rem;color:#555;margin-top:6px;line-height:1.7;">
                                Survey: {land.survey_number}<br/>
                                GPS: {land.gps_lat:.4f}, {land.gps_lon:.4f}<br/>
                                Soil: {land.soil_type}<br/>
                                Irrigation: {land.irrigation_type}<br/>
                                Area: {land.area_hectares:.2f} ha
                            </div>
                        </div>""", unsafe_allow_html=True)

                with right:
                    # Soil Health Card
                    sh = detail.get("soil_health")
                    if sh:
                        st.markdown(f"""
                        <div style="background:#fff;border:1px solid #e0dcd5;border-radius:8px;padding:16px;">
                            <div style="font-weight:600;color:#666;font-size:0.75rem;text-transform:uppercase;letter-spacing:1px;">Soil Health Card</div>
                            <div style="font-size:0.85rem;color:#555;margin-top:6px;line-height:1.7;">
                                pH: {sh.pH:.1f} · Classification: {sh.classification}<br/>
                                N/P/K: {sh.nitrogen_kg_ha:.0f} / {sh.phosphorus_kg_ha:.0f} / {sh.potassium_kg_ha:.0f} kg/ha<br/>
                                Organic Carbon: {sh.organic_carbon_pct:.1f}%
                            </div>
                        </div>""", unsafe_allow_html=True)

                    # PM-KISAN
                    pmk = detail.get("pmkisan")
                    if pmk:
                        st.markdown(f"""
                        <div style="background:#fff;border:1px solid #e0dcd5;border-radius:8px;padding:16px;margin-top:10px;">
                            <div style="font-weight:600;color:#666;font-size:0.75rem;text-transform:uppercase;letter-spacing:1px;">PM-KISAN</div>
                            <div style="font-size:0.85rem;color:#555;margin-top:6px;line-height:1.7;">
                                Installments received: {pmk.installments_received}<br/>
                                Total amount: Rs {pmk.total_amount:,.0f}
                            </div>
                        </div>""", unsafe_allow_html=True)

                    # PMFBY Insurance
                    ins = detail.get("pmfby")
                    if ins:
                        st.markdown(f"""
                        <div style="background:#fff;border:1px solid #e0dcd5;border-radius:8px;padding:16px;margin-top:10px;">
                            <div style="font-weight:600;color:#666;font-size:0.75rem;text-transform:uppercase;letter-spacing:1px;">PMFBY Crop Insurance</div>
                            <div style="font-size:0.85rem;color:#555;margin-top:6px;line-height:1.7;">
                                Status: {ins.status}<br/>
                                Sum insured: Rs {ins.sum_insured:,.0f}<br/>
                                Premium paid: Rs {ins.premium_paid:,.0f}
                            </div>
                        </div>""", unsafe_allow_html=True)

                    # KCC
                    kcc = detail.get("kcc")
                    if kcc:
                        st.markdown(f"""
                        <div style="background:#fff;border:1px solid #e0dcd5;border-radius:8px;padding:16px;margin-top:10px;">
                            <div style="font-weight:600;color:#666;font-size:0.75rem;text-transform:uppercase;letter-spacing:1px;">Kisan Credit Card</div>
                            <div style="font-size:0.85rem;color:#555;margin-top:6px;line-height:1.7;">
                                Credit limit: Rs {kcc.credit_limit:,.0f}<br/>
                                Outstanding: Rs {kcc.outstanding:,.0f}<br/>
                                Repayment: {kcc.repayment_status}
                            </div>
                        </div>""", unsafe_allow_html=True)

                # Show latest advisory for this farmer's station
                station_id = farmer["station_id"]
                station_alerts = alerts[alerts["station_id"] == station_id]
                if not station_alerts.empty:
                    st.markdown('<div class="section-header">Latest Advisory for This Farmer</div>',
                                unsafe_allow_html=True)
                    latest = station_alerts.iloc[0]
                    cond = latest.get("condition") or "clear"
                    color = CONDITION_COLOR.get(cond, "#888")
                    text = str(latest.get("advisory_local") or latest.get("advisory_en", ""))
                    st.markdown(f"""
                    <div style="background:#fff;border:1px solid #e0dcd5;border-left:3px solid {color};
                                border-radius:8px;padding:14px;">
                        <span style="background:{color};color:#fff;padding:2px 8px;border-radius:10px;
                                     font-size:0.7rem;font-weight:600;">{cond.replace('_', ' ').title()}</span>
                        <span style="color:#888;font-size:0.75rem;margin-left:8px;">
                            {latest.get('provider', '')} · {latest.get('language', '')}</span>
                        <div style="color:#555;font-size:0.85rem;line-height:1.5;margin-top:8px;">
                            {text[:300]}
                        </div>
                    </div>""", unsafe_allow_html=True)

# ========================== DELIVERY ==========================
with tab_delivery:
    st.markdown('<div class="section-header">Delivery Status</div>',
                unsafe_allow_html=True)

    if delivery.empty:
        st.info("No deliveries logged yet.")
    else:
        c1, c2, c3, c4 = st.columns(4)
        sent = delivery["status"].isin(["sent", "dry_run"]).sum() if "status" in delivery.columns else 0
        failed = (delivery["status"] == "failed").sum() if "status" in delivery.columns else 0
        channels = delivery["channel"].nunique() if "channel" in delivery.columns else 0
        recipients = delivery["recipient"].nunique() if "recipient" in delivery.columns else 0
        c1.metric("Sent / Dry-run", sent)
        c2.metric("Failed", failed)
        c3.metric("Channels", channels)
        c4.metric("Recipients", recipients)

        # Delivery log table
        show_cols = [c for c in ["station_id", "channel", "recipient", "status", "message", "delivered_at"]
                     if c in delivery.columns]
        df_del = delivery[show_cols].head(30).copy()
        if "message" in df_del.columns:
            df_del["message"] = df_del["message"].astype(str).str[:80]

        def _status_style(val):
            if val in ("sent", "dry_run"):
                return "background-color: rgba(42,157,143,0.15); color: #2a9d8f"
            elif val == "failed":
                return "background-color: rgba(230,57,70,0.12); color: #e63946"
            return ""

        if "status" in df_del.columns:
            st.dataframe(
                df_del.style.map(_status_style, subset=["status"]),
                width="stretch", hide_index=True,
            )
        else:
            st.dataframe(df_del, width="stretch", hide_index=True)

# Chat toggle
from streamlit_app.chat_widget import render_chat_toggle
render_chat_toggle()
