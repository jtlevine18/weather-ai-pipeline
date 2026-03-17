"""Chat page — NL agent interface embedded in Streamlit."""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import streamlit as st

from streamlit_app.style import inject_css

st.set_page_config(page_title="Chat Agent", page_icon="💬", layout="wide")
inject_css()

st.markdown("""
<style>
[data-testid="stChatMessage"][data-testid*="user"] {
    background: #f0ede8 !important;
}
</style>
""", unsafe_allow_html=True)

st.title("💬 Weather Pipeline Chat")
st.caption("Conversational pipeline management powered by Claude")

# ---------------------------------------------------------------------------
# Load agent
# ---------------------------------------------------------------------------
@st.cache_resource
def _load_agent():
    from config import get_config
    from src.nl_agent import NLAgent
    config = get_config()
    if not config.anthropic_key:
        return None
    return NLAgent(config)

agent = _load_agent()

if agent is None:
    st.warning("ANTHROPIC_API_KEY is not set. Add it to your `.env` file or Streamlit secrets to enable the chat agent.")
    st.markdown(
        "The chat agent can check station health, run forecasts, show pipeline metrics, "
        "and answer questions about the weather data — all through natural language."
    )
    st.chat_input("Ask about the pipeline…", disabled=True)
    st.stop()

# ---------------------------------------------------------------------------
# Session state — includes initial greeting message like weather AI 1
# ---------------------------------------------------------------------------
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = [{
        "role": "assistant",
        "content": (
            "I'm your Weather AI assistant for Kerala and Tamil Nadu. "
            "I can check station health, run forecasts, show pipeline metrics, "
            "and explain the architecture. What would you like to know?"
        ),
    }]

# ---------------------------------------------------------------------------
# Sidebar — quick prompts + clear button
# ---------------------------------------------------------------------------
with st.sidebar:
    if st.button("🗑️ Clear conversation", use_container_width=True):
        st.session_state.chat_messages = [{
            "role": "assistant",
            "content": (
                "I'm your Weather AI assistant for Kerala and Tamil Nadu. "
                "I can check station health, run forecasts, show pipeline metrics, "
                "and explain the architecture. What would you like to know?"
            ),
        }]
        st.rerun()

    st.divider()
    st.markdown("**Quick prompts**")
    quick_prompts = [
        "What is the pipeline status?",
        "Which stations have heat stress?",
        "Show me the latest Kerala advisories.",
        "How does the architecture work?",
    ]
    for qp in quick_prompts:
        if st.button(qp, key=f"qp_{qp}", use_container_width=True):
            st.session_state["_pending_prompt"] = qp
            st.rerun()

# ---------------------------------------------------------------------------
# Render conversation history
# ---------------------------------------------------------------------------
for msg in st.session_state.chat_messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# ---------------------------------------------------------------------------
# Handle input (typed or quick-prompt injection)
# ---------------------------------------------------------------------------
user_input = None
if "_pending_prompt" in st.session_state:
    user_input = st.session_state.pop("_pending_prompt")
else:
    user_input = st.chat_input("Ask about the weather pipeline…")

if user_input:
    st.session_state.chat_messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        with st.spinner("Thinking…"):
            try:
                history = [
                    {"role": m["role"], "content": m["content"]}
                    for m in st.session_state.chat_messages[:-1]
                ]
                response = agent.chat(user_input, history)
                st.markdown(response)
                st.session_state.chat_messages.append(
                    {"role": "assistant", "content": response}
                )
            except Exception as exc:
                err = f"Error: {exc}"
                st.error(err)
                st.session_state.chat_messages.append(
                    {"role": "assistant", "content": err}
                )
