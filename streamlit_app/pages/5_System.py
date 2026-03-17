"""System page — architecture diagram, pipeline runs, delivery log, cost estimate."""

import os
import sys
import json as json_mod
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd

from streamlit_app.style import inject_css
from streamlit_app.data_helpers import load_pipeline_runs, load_delivery_log

st.set_page_config(page_title="System", page_icon="⚙️", layout="wide")
inject_css()

st.title("⚙️ System Overview")
st.caption("Architecture, pipeline run history, and cost estimate")

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_arch, tab_runs, tab_delivery, tab_cost = st.tabs([
    "Architecture", "Pipeline Runs", "Delivery Log", "Cost Estimate"
])

# ========================== ARCHITECTURE ==========================
with tab_arch:
    from src.architecture import generate_mermaid, get_architecture_text

    mermaid_code    = generate_mermaid()
    mermaid_escaped = json_mod.dumps(mermaid_code)

    mermaid_html = f"""<!DOCTYPE html>
<html>
<head>
  <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
</head>
<body style="background:#faf8f5;margin:0;padding:8px;">
  <div id="diagram" style="display:flex;justify-content:center;"></div>
  <script>
    mermaid.initialize({{
      startOnLoad: false,
      theme: 'base',
      themeVariables: {{
        primaryColor: '#ffffff',
        primaryBorderColor: '#e0dcd5',
        primaryTextColor: '#1a1a1a',
        lineColor: '#d4a019',
        secondaryColor: '#f0ede8',
        tertiaryColor: '#faf8f5',
        fontFamily: 'Inter, Segoe UI, sans-serif'
      }},
      securityLevel: 'loose'
    }});
    (async function() {{
      try {{
        const code = {mermaid_escaped};
        const {{ svg }} = await mermaid.render('arch-diagram', code);
        document.getElementById('diagram').innerHTML = svg;
      }} catch(e) {{
        document.getElementById('diagram').innerHTML =
          '<p style="color:#e63946;font-family:Inter,sans-serif;">Diagram error: ' + e.message + '</p>';
      }}
    }})();
  </script>
</body>
</html>"""

    components.html(mermaid_html, height=820, scrolling=True)
    st.caption("Architecture diagram generated dynamically from `src/architecture.py`")

    with st.expander("Plain-text description"):
        st.code(get_architecture_text(), language=None)


# ========================== PIPELINE RUNS ==========================
with tab_runs:
    runs = load_pipeline_runs(limit=20)
    if runs.empty:
        st.info("No pipeline runs recorded yet. Run `python run_pipeline.py` to generate data.")
    else:
        total    = len(runs)
        ok_count = (runs["status"] == "ok").sum() if "status" in runs.columns else 0

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Runs", total)
        with col2:
            st.metric("Successful", ok_count)
        with col3:
            st.metric("Partial / Failed", total - ok_count)

        display_cols = [c for c in [
            "id", "started_at", "ended_at", "status", "steps_ok", "steps_fail", "summary"
        ] if c in runs.columns]
        df_show = runs[display_cols].copy()
        if "id" in df_show.columns:
            df_show["id"] = df_show["id"].str[:8]

        STATUS_COLOR = {"ok": "#2a9d8f", "partial": "#f4a261", "failed": "#e63946"}
        rows_html = ""
        for _, row in df_show.iterrows():
            status = row.get("status", "?")
            color  = STATUS_COLOR.get(status, "#888")
            rid    = str(row.get("id", ""))
            start  = str(row.get("started_at", ""))[:16]
            ok_s   = row.get("steps_ok", "")
            fail_s = row.get("steps_fail", "")
            summ   = str(row.get("summary", ""))[:80]
            rows_html += (
                f"<tr style='border-bottom:1px solid #f0ede8;'>"
                f"<td style='padding:6px 10px;'>"
                f"<span style='background:{color};color:#fff;padding:2px 8px;border-radius:3px;"
                f"font-size:0.7rem;font-weight:600'>{status}</span></td>"
                f"<td style='padding:6px 10px;font-family:monospace;color:#666;font-size:0.8rem'>{rid}</td>"
                f"<td style='padding:6px 10px;color:#555;font-size:0.82rem'>{start}</td>"
                f"<td style='padding:6px 10px;color:#2a9d8f;font-size:0.82rem'>{ok_s}</td>"
                f"<td style='padding:6px 10px;color:#e63946;font-size:0.82rem'>{fail_s}</td>"
                f"<td style='padding:6px 10px;color:#333;font-size:0.82rem'>{summ}</td>"
                f"</tr>"
            )
        th = "padding:8px 10px;text-align:left;font-size:0.72rem;text-transform:uppercase;letter-spacing:1px;color:#666;"
        st.markdown(
            f'<table style="width:100%;border-collapse:collapse;background:#fff;'
            f'border:1px solid #e0dcd5;border-radius:8px;overflow:hidden;margin-top:12px;">'
            f'<thead><tr style="background:#f5f3ef;border-bottom:2px solid #e0dcd5;">'
            f'<th style="{th}">Status</th><th style="{th}">Run ID</th>'
            f'<th style="{th}">Started</th><th style="{th}">Steps OK</th>'
            f'<th style="{th}">Failed</th><th style="{th}">Summary</th>'
            f'</tr></thead><tbody>{rows_html}</tbody></table>',
            unsafe_allow_html=True,
        )

# ========================== DELIVERY LOG ==========================
with tab_delivery:
    delivery = load_delivery_log(limit=100)
    if delivery.empty:
        st.info("No deliveries logged yet.")
    else:
        col1, col2, col3 = st.columns(3)
        with col1:
            sent = delivery["status"].isin(["sent", "dry_run"]).sum() if "status" in delivery.columns else 0
            st.metric("Sent / Dry-run", sent)
        with col2:
            failed = (delivery["status"] == "failed").sum() if "status" in delivery.columns else 0
            st.metric("Failed", failed)
        with col3:
            channels = delivery["channel"].nunique() if "channel" in delivery.columns else 0
            st.metric("Channels Used", channels)

        display_cols = [c for c in [
            "station_id", "channel", "recipient", "status", "message", "delivered_at"
        ] if c in delivery.columns]
        df_dl = delivery[display_cols].head(30).copy()
        if "message" in df_dl.columns:
            df_dl["message"] = df_dl["message"].str[:80]
        st.dataframe(df_dl, use_container_width=True, hide_index=True)

# ========================== COST ESTIMATE ==========================
with tab_cost:
    st.subheader("API Cost Estimate (per pipeline run)")

    cost_data = {
        "Component": [
            "Tomorrow.io (20 station heal calls)",
            "Open-Meteo NWP (20 calls)",
            "NASA POWER heal fallback (up to 20)",
            "NASA POWER downscaling (20×25 grid = 500)",
            "Claude advisory generation (20 × ~400 tokens out)",
            "Claude translation (20 × ~300 tokens out)",
        ],
        "Unit Cost": [
            "Free tier / $0.001",
            "Free",
            "Free",
            "Free",
            "~$0.003 / call",
            "~$0.003 / call",
        ],
        "Est. per Run": [
            "~$0.02",
            "$0.00",
            "$0.00",
            "$0.00",
            "~$0.06",
            "~$0.06",
        ],
        "Notes": [
            "500 free calls/day; ~$0.001 for overage",
            "Fully free API",
            "Free NASA public API",
            "Free NASA public API",
            "claude-sonnet-4-6 @ $3/M in · $15/M out",
            "Separate Claude call per station",
        ],
    }

    st.table(pd.DataFrame(cost_data))

    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        st.markdown('<div class="section-header">Per-Run Totals</div>', unsafe_allow_html=True)
        st.markdown(
            "<div style='background:#fff;border:1px solid #e0dcd5;border-radius:8px;padding:16px;'>"
            "<div style='font-size:2rem;font-weight:700;color:#d4a019;'>~$0.14</div>"
            "<div style='color:#666;font-size:0.82rem;margin-top:4px;'>per pipeline run (20 stations, Claude on)</div>"
            "<div style='color:#2a9d8f;font-size:0.82rem;margin-top:4px;'>~$0.02 per run (rule-based only)</div>"
            "</div>",
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown('<div class="section-header">Monthly Estimate (4× / day)</div>', unsafe_allow_html=True)
        st.markdown(
            "<div style='background:#fff;border:1px solid #e0dcd5;border-radius:8px;padding:16px;'>"
            "<div style='font-size:2rem;font-weight:700;color:#1a1a1a;'>~$17 / month</div>"
            "<div style='color:#666;font-size:0.82rem;margin-top:4px;'>running Claude advisories 4× daily</div>"
            "<div style='color:#2a9d8f;font-size:0.82rem;margin-top:4px;'>~$2.40 / month (rule-based fallback)</div>"
            "</div>",
            unsafe_allow_html=True,
        )

    st.caption("Based on claude-sonnet-4-6 pricing (~$3/M input, $15/M output tokens). "
               "Actual cost varies with RAG context length.")
