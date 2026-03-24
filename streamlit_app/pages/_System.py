"""System page — architecture diagram, pipeline runs, delivery log, cost estimate."""

import os
import sys
import json as json_mod
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd

from streamlit_app.style import inject_css, inject_sidebar_nav, STATUS_COLOR
from streamlit_app.data_helpers import (load_pipeline_runs, load_delivery_log,
                                        load_conversation_log, load_delivery_metrics)

st.set_page_config(page_title="System", page_icon="S", layout="wide")
inject_css()
inject_sidebar_nav()

st.title("System Overview")
st.caption("Architecture, pipeline run history, and cost estimate")

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_arch, tab_sched, tab_runs, tab_delivery, tab_cost, tab_eval, tab_agent, tab_funnel = st.tabs([
    "Architecture", "Scheduler", "Pipeline Runs", "Delivery Log", "Cost Estimate",
    "Eval Metrics", "Agent Log", "Delivery Funnel"
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


# ========================== SCHEDULER ==========================
with tab_sched:
    from src.daily_scheduler import is_enabled as _sched_enabled, is_running as _sched_running
    from src.daily_scheduler import start as _sched_start, stop as _sched_stop, next_run_time

    current_enabled = _sched_enabled()

    st.subheader("Daily Pipeline Scheduler")
    st.caption("Runs the full 6-step pipeline once per day at 6:00 AM IST (background thread)")

    new_enabled = st.toggle("Enable daily pipeline run", value=current_enabled)

    if new_enabled != current_enabled:
        if new_enabled:
            _sched_start()
        else:
            _sched_stop()
        st.rerun()

    if current_enabled:
        running = _sched_running()
        if running:
            nrt = next_run_time()
            next_str = nrt.strftime("%Y-%m-%d %H:%M UTC") if nrt else "calculating..."
            st.success(f"Scheduler is **active** — next run: {next_str}")
        else:
            st.warning("State is enabled but scheduler thread is not running. "
                       "Toggle off and on to restart.")
    else:
        st.info("Scheduler is **off** — toggle on to start daily runs")

    st.divider()

    st.markdown(
        "<div style='background:#fff;border:1px solid #e0dcd5;border-radius:8px;padding:16px;'>"
        "<div style='font-size:0.82rem;color:#666;'>Schedule</div>"
        "<div style='font-size:1.1rem;font-weight:600;color:#1a1a1a;'>Every day at 6:00 AM IST</div>"
        "<div style='font-size:0.78rem;color:#888;margin-top:6px;'>"
        "APScheduler background thread (cron: 00:30 UTC)<br>"
        "State persists in <code>scheduler_state.json</code> — auto-resumes after restart</div>"
        "</div>",
        unsafe_allow_html=True,
    )

    st.divider()
    last_runs = load_pipeline_runs(limit=3)
    if not last_runs.empty:
        st.markdown('<div class="section-header">Recent Runs</div>', unsafe_allow_html=True)
        for _, row in last_runs.iterrows():
            status = row.get("status", "?")
            color = STATUS_COLOR.get(status, "#888")
            started = str(row.get("started_at", ""))[:16]
            st.markdown(
                f"<span style='background:{color};color:#fff;padding:2px 8px;border-radius:3px;"
                f"font-size:0.7rem;font-weight:600'>{status}</span>"
                f"&nbsp;&nbsp;<span style='color:#555;font-size:0.82rem'>{started}</span>",
                unsafe_allow_html=True,
            )
    else:
        st.caption("No pipeline runs recorded yet.")

    st.divider()
    st.markdown('<div class="section-header">Manual Controls</div>', unsafe_allow_html=True)

    bc1, bc2, bc3, bc4 = st.columns(4)

    with bc1:
        if st.button("Run Full Pipeline", use_container_width=True,
                      help="All 6 steps: ingest → heal → forecast → downscale → translate → deliver"):
            with st.spinner("Running all 6 steps..."):
                try:
                    import asyncio as _aio
                    from config import get_config
                    from src.pipeline import WeatherPipeline
                    p = WeatherPipeline(get_config())
                    r = _aio.run(p.run())
                    st.success(f"{r.get('alerts', 0)} alerts in {r.get('elapsed_s', 0):.0f}s")
                    st.cache_data.clear()
                except Exception as exc:
                    st.error(f"Pipeline error: {exc}")

    with bc2:
        if st.button("Ingest + Heal", use_container_width=True,
                      help="Steps 1–2: fetch fresh IMD data and cross-validate"):
            with st.spinner("Running ingest + heal..."):
                try:
                    import asyncio as _aio
                    from config import get_config
                    from src.pipeline import WeatherPipeline
                    p = WeatherPipeline(get_config())

                    async def _ingest_heal():
                        raw = await p.step_ingest()
                        clean = await p.step_heal(raw)
                        return len(raw), len(clean)

                    n_raw, n_clean = _aio.run(_ingest_heal())
                    st.success(f"Ingested {n_raw} readings, healed → {n_clean}")
                    st.cache_data.clear()
                except Exception as exc:
                    st.error(f"Error: {exc}")

    with bc3:
        if st.button("Forecast → Deliver", use_container_width=True,
                      help="Steps 3–6: forecast, downscale, translate, deliver from existing data"):
            with st.spinner("Running forecast → deliver..."):
                try:
                    import asyncio as _aio
                    from config import get_config
                    from src.pipeline import WeatherPipeline
                    p = WeatherPipeline(get_config())

                    async def _forecast_deliver():
                        fc = await p.step_forecast()
                        ds = await p.step_downscale(fc)
                        alerts = await p.step_translate(ds)
                        delivered = await p.step_deliver(alerts)
                        return len(fc), len(alerts), delivered

                    n_fc, n_alerts, n_del = _aio.run(_forecast_deliver())
                    st.success(f"{n_fc} forecasts → {n_alerts} alerts → {n_del} delivered")
                    st.cache_data.clear()
                except Exception as exc:
                    st.error(f"Error: {exc}")

    with bc4:
        if st.button("Retrain MOS Model", use_container_width=True,
                      help="Export day-0 forecast/obs pairs from PostgreSQL and retrain the XGBoost MOS model"):
            with st.spinner("Exporting data and training model..."):
                try:
                    import subprocess
                    subprocess.run(
                        [sys.executable, "scripts/export_training_data.py"],
                        check=True, capture_output=True, text=True,
                        cwd=os.path.join(os.path.dirname(__file__), "..", ".."),
                    )
                    result = subprocess.run(
                        [sys.executable, "scripts/train_mos.py"],
                        check=True, capture_output=True, text=True,
                        cwd=os.path.join(os.path.dirname(__file__), "..", ".."),
                    )
                    st.success("MOS model retrained successfully")
                except subprocess.CalledProcessError as exc:
                    st.error(f"Training failed: {(exc.stderr or exc.stdout or str(exc))[:300]}")


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

# ========================== EVAL METRICS ==========================
with tab_eval:
    from streamlit_app.data_helpers import load_eval_results
    evals = load_eval_results()

    if not evals:
        st.info(
            "No eval results found yet. Run the eval scripts from the project root:"
        )
        st.code(
            "python tests/eval_healing.py         # Self-healing detection accuracy\n"
            "python tests/eval_forecast.py        # Forecast accuracy (MAE/RMSE)\n"
            "python tests/eval_rag.py             # RAG retrieval precision/recall\n"
            "python tests/eval_advisory.py        # Advisory quality scoring\n"
            "python tests/eval_translation.py     # Translation quality\n"
            "python tests/eval_dpi.py             # DPI profile coverage & realism\n"
            "python tests/eval_conversation.py    # Conversation engine quality",
            language="bash",
        )
    else:
        # ---- Healing ----
        if "healing" in evals:
            st.subheader("Self-Healing Detection")
            h = evals["healing"]
            bd = h.get("binary_detection", {})
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Precision", f"{bd.get('precision', 0):.0%}")
            c2.metric("Recall", f"{bd.get('recall', 0):.0%}")
            c3.metric("F1", f"{bd.get('f1', 0):.0%}")
            c4.metric("Total Readings", h.get("total_readings", 0))

            pft = h.get("per_fault_type", {})
            if pft:
                pft_rows = []
                for ft, m in pft.items():
                    pft_rows.append({
                        "Fault Type": ft,
                        "Count": m.get("count", 0),
                        "Detection Rate": (f"{m['accuracy']:.0%}"
                                           if m.get("accuracy") is not None else "N/A"),
                        "Imputation MAE": (f"{m['imputation_mae']:.2f}"
                                           if m.get("imputation_mae") is not None else "---"),
                    })
                st.dataframe(pd.DataFrame(pft_rows),
                             hide_index=True, use_container_width=True)
            st.divider()

        # ---- Forecast ----
        if "forecast" in evals:
            st.subheader("Forecast Accuracy")
            f_eval = evals["forecast"]
            overall = f_eval.get("overall", {})
            temp = overall.get("temperature", {})
            c1, c2, c3 = st.columns(3)
            c1.metric("Temp MAE",
                       f"{temp['mae']:.2f} C" if temp.get("mae") else "---")
            c2.metric("Temp RMSE",
                       f"{temp['rmse']:.2f} C" if temp.get("rmse") else "---")
            c3.metric("Paired Records", f_eval.get("total_pairs", 0))

            by_model = f_eval.get("by_model", {})
            if by_model:
                model_rows = [
                    {"Model": mt, "N": m.get("n", 0),
                     "MAE (C)": f"{m['mae']:.2f}" if m.get("mae") else "---",
                     "RMSE (C)": f"{m['rmse']:.2f}" if m.get("rmse") else "---",
                     "Bias (C)": f"{m['bias']:+.2f}" if m.get("bias") is not None else "---"}
                    for mt, m in by_model.items()
                ]
                st.dataframe(pd.DataFrame(model_rows),
                             hide_index=True, use_container_width=True)
            st.divider()

        # ---- RAG ----
        if "rag" in evals:
            st.subheader("RAG Retrieval Quality")
            by_mode = evals["rag"].get("by_mode", {})
            if by_mode:
                rag_rows = [
                    {"Mode": mode,
                     "Avg Precision@5": f"{m.get('avg_precision', 0):.2f}",
                     "Avg Recall": f"{m.get('avg_recall', 0):.2f}",
                     "Cases": m.get("n_cases", 0)}
                    for mode, m in by_mode.items()
                ]
                st.dataframe(pd.DataFrame(rag_rows),
                             hide_index=True, use_container_width=True)
            st.divider()

        # ---- Advisory ----
        if "advisory" in evals:
            st.subheader("Advisory Quality")
            by_prov = evals["advisory"].get("by_provider", {})
            if by_prov:
                adv_rows = [
                    {"Provider": prov,
                     "Accuracy": f"{m.get('avg_accuracy', 0):.1f}/5",
                     "Actionability": f"{m.get('avg_actionability', 0):.1f}/5",
                     "Safety": f"{m.get('avg_safety', 0):+.1f}",
                     "Cultural": f"{m.get('avg_cultural', 0):.1f}/5"}
                    for prov, m in by_prov.items()
                ]
                st.dataframe(pd.DataFrame(adv_rows),
                             hide_index=True, use_container_width=True)
            st.divider()

        # ---- Translation ----
        if "translation" in evals:
            st.subheader("Translation Quality")
            t_eval = evals["translation"]
            c1, c2 = st.columns(2)
            c1.metric("Semantic Similarity",
                       f"{t_eval.get('avg_similarity', 0):.1f}/5")
            c2.metric("Ag Term Preservation",
                       f"{t_eval.get('avg_ag_preservation', 0):.0%}")

            by_lang = t_eval.get("by_language", {})
            if by_lang:
                lang_rows = [
                    {"Language": {"ta": "Tamil", "ml": "Malayalam"}.get(lang, lang),
                     "N": m.get("n", 0),
                     "Similarity": f"{m.get('avg_similarity', 0):.1f}/5",
                     "Ag Preservation": f"{m.get('avg_ag_preservation', 0):.0%}"}
                    for lang, m in by_lang.items()
                ]
                st.dataframe(pd.DataFrame(lang_rows),
                             hide_index=True, use_container_width=True)

        # ---- DPI ----
        if "dpi" in evals:
            st.subheader("DPI Profile Quality")
            d_eval = evals["dpi"]
            cov = d_eval.get("coverage", {})
            comp = d_eval.get("completeness", {})
            geo = d_eval.get("geographic_realism", {})
            con = d_eval.get("consistency", {})

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Farmers", d_eval.get("total_farmers", 0))
            c2.metric("Station Coverage", f"{cov.get('coverage_rate', 0):.0%}")
            c3.metric("Completeness", f"{comp.get('completeness_rate', 0):.0%}")
            c4.metric("Consistency", f"{con.get('rate', 0):.0%}")

            geo_rows = [
                {"Check": "Crop-region match", "Rate": f"{geo.get('crop_match_rate', 0):.0%}"},
                {"Check": "Soil pH realism", "Rate": f"{geo.get('ph_match_rate', 0):.0%}"},
            ]
            st.dataframe(pd.DataFrame(geo_rows),
                         hide_index=True, use_container_width=True)
            st.divider()

        # ---- Conversation ----
        if "conversation" in evals:
            st.subheader("Conversation Engine")
            c_eval = evals["conversation"]
            sm = c_eval.get("state_machine", {})
            ld = c_eval.get("language_detection", {})
            esc = c_eval.get("escalation_detection", {})
            ov = c_eval.get("overall", {})

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("State Machine", f"{sm.get('accuracy', 0):.0%}")
            c2.metric("Language Detection", f"{ld.get('accuracy', 0):.0%}")
            c3.metric("Escalation Detection", f"{esc.get('accuracy', 0):.0%}")
            c4.metric("Overall", f"{ov.get('overall_rate', 0):.0%}")

            tools_info = c_eval.get("tools", {})
            if tools_info:
                st.caption(f"Tools: {tools_info.get('nl_tools', 0)} NL + "
                          f"{tools_info.get('conversation_tools', 0)} conversation = "
                          f"{tools_info.get('total', 0)} total")

            pers = c_eval.get("personalization", {})
            if pers and not pers.get("skipped"):
                st.metric("Personalization Uplift",
                          f"{pers.get('avg_uplift', 0):.1f}/5")
            st.divider()

        st.caption("Run eval scripts from the project root to update these metrics.")

# ========================== AGENT LOG ==========================
with tab_agent:
    conv_log = load_conversation_log(limit=200)
    if conv_log.empty:
        st.info("No conversation logs yet. Use the Chat page or `python run_chat.py` to generate data.")
    else:
        # Aggregate metrics
        total_queries = len(conv_log[conv_log["role"] == "user"]) if "role" in conv_log.columns else 0
        total_responses = len(conv_log[conv_log["role"] == "assistant"]) if "role" in conv_log.columns else 0
        sessions = conv_log["session_id"].nunique() if "session_id" in conv_log.columns else 0

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Sessions", sessions)
        c2.metric("User Queries", total_queries)
        c3.metric("Responses", total_responses)

        if "latency_ms" in conv_log.columns:
            assistant_rows = conv_log[conv_log["role"] == "assistant"]
            valid_latency = assistant_rows["latency_ms"].dropna()
            avg_latency = int(valid_latency.mean()) if len(valid_latency) > 0 else 0
            c4.metric("Avg Latency", f"{avg_latency} ms")
        else:
            c4.metric("Avg Latency", "---")

        # Token usage
        if "tokens_in" in conv_log.columns and "tokens_out" in conv_log.columns:
            total_in = int(conv_log["tokens_in"].sum()) if conv_log["tokens_in"].notna().any() else 0
            total_out = int(conv_log["tokens_out"].sum()) if conv_log["tokens_out"].notna().any() else 0
            tc1, tc2 = st.columns(2)
            tc1.metric("Total Input Tokens", f"{total_in:,}")
            tc2.metric("Total Output Tokens", f"{total_out:,}")

        # Most-used tools
        tool_rows = conv_log[conv_log["role"] == "tool_use"] if "role" in conv_log.columns else pd.DataFrame()
        if not tool_rows.empty and "tool_name" in tool_rows.columns:
            st.subheader("Tool Usage")
            tool_counts = tool_rows["tool_name"].value_counts().reset_index()
            tool_counts.columns = ["Tool", "Count"]
            st.dataframe(tool_counts, hide_index=True, use_container_width=True)

        # Recent conversations
        st.subheader("Recent Conversations")
        user_msgs = conv_log[conv_log["role"] == "user"].copy() if "role" in conv_log.columns else pd.DataFrame()
        if not user_msgs.empty:
            display_cols = [c for c in ["session_id", "content", "created_at"]
                           if c in user_msgs.columns]
            df_show = user_msgs[display_cols].head(20).copy()
            if "session_id" in df_show.columns:
                df_show["session_id"] = df_show["session_id"].str[:8]
            if "content" in df_show.columns:
                df_show["content"] = df_show["content"].str[:100]
            df_show.columns = ["Session", "Query", "Time"][:len(display_cols)]
            st.dataframe(df_show, hide_index=True, use_container_width=True)

# ========================== DELIVERY FUNNEL ==========================
with tab_funnel:
    dm = load_delivery_metrics(limit=500)
    if dm.empty:
        st.info("No delivery metrics yet. Run `python run_pipeline.py` to generate data.")
    else:
        # Aggregate funnel
        total_stations = dm["station_id"].nunique() if "station_id" in dm.columns else 0
        total_forecasts = int(dm["forecasts_generated"].sum()) if "forecasts_generated" in dm.columns else 0
        total_advisories = int(dm["advisories_generated"].sum()) if "advisories_generated" in dm.columns else 0
        total_attempted = int(dm["deliveries_attempted"].sum()) if "deliveries_attempted" in dm.columns else 0
        total_succeeded = int(dm["deliveries_succeeded"].sum()) if "deliveries_succeeded" in dm.columns else 0

        st.subheader("Delivery Funnel")
        funnel_data = [
            ("Stations", total_stations),
            ("Forecasts", total_forecasts),
            ("Advisories", total_advisories),
            ("Deliveries Attempted", total_attempted),
            ("Deliveries Succeeded", total_succeeded),
        ]

        # Horizontal funnel metrics
        cols = st.columns(len(funnel_data))
        for col, (label, val) in zip(cols, funnel_data):
            col.metric(label, val)

        # Funnel bar visualization
        funnel_df = pd.DataFrame(funnel_data, columns=["Stage", "Count"])
        st.bar_chart(funnel_df.set_index("Stage"))

        # Per-station breakdown
        st.subheader("Per-Station Breakdown")
        station_agg = dm.groupby("station_id").agg(
            forecasts=("forecasts_generated", "sum"),
            advisories=("advisories_generated", "sum"),
            attempted=("deliveries_attempted", "sum"),
            succeeded=("deliveries_succeeded", "sum"),
        ).reset_index()
        station_agg["success_rate"] = (
            (station_agg["succeeded"] / station_agg["attempted"].replace(0, 1)) * 100
        ).round(1)
        station_agg.columns = ["Station", "Forecasts", "Advisories",
                               "Attempted", "Succeeded", "Success %"]
        st.dataframe(station_agg, hide_index=True, use_container_width=True)

# Chat toggle
from streamlit_app.chat_widget import render_chat_toggle
render_chat_toggle()
