"""Chat page — Conversational agent interface with farmer identity."""

import asyncio
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import uuid

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
# Load agents
# ---------------------------------------------------------------------------
@st.cache_resource
def _load_config():
    from config import get_config
    return get_config()

config = _load_config()

if not config.anthropic_key:
    st.warning("ANTHROPIC_API_KEY is not set. Add it to your `.env` file or Streamlit secrets to enable the chat agent.")
    st.chat_input("Ask about the pipeline…", disabled=True)
    st.stop()

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
if "chat_session_id" not in st.session_state:
    st.session_state.chat_session_id = str(uuid.uuid4())

if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = [{
        "role": "assistant",
        "content": (
            "I'm your Weather AI assistant for Kerala and Tamil Nadu. "
            "I can check station health, run forecasts, show pipeline metrics, "
            "and explain the architecture. Enter a phone number in the sidebar "
            "to access personalized farmer services."
        ),
    }]

if "farmer_phone" not in st.session_state:
    st.session_state.farmer_phone = ""
if "farmer_identified" not in st.session_state:
    st.session_state.farmer_identified = False
if "farmer_info" not in st.session_state:
    st.session_state.farmer_info = None
if "agent_mode" not in st.session_state:
    st.session_state.agent_mode = "generic"

# ---------------------------------------------------------------------------
# Sidebar — farmer identity + quick prompts
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("**Farmer Identity**")
    phone_input = st.text_input("Phone number", value=st.session_state.farmer_phone,
                                placeholder="+919876543210")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Look up", use_container_width=True):
            if phone_input.strip():
                st.session_state.farmer_phone = phone_input.strip()
                with st.spinner("Identifying..."):
                    try:
                        from src.dpi.simulator import get_registry
                        registry = get_registry()
                        profile = registry.lookup_by_phone(phone_input.strip())
                        if profile:
                            st.session_state.farmer_identified = True
                            st.session_state.farmer_info = {
                                "name": profile.aadhaar.name,
                                "name_local": profile.aadhaar.name_local,
                                "district": profile.aadhaar.district,
                                "state": profile.aadhaar.state,
                                "language": profile.aadhaar.language,
                                "crops": profile.primary_crops,
                                "area": profile.total_area,
                                "aadhaar_id": profile.aadhaar.aadhaar_id,
                            }
                            st.session_state.agent_mode = "conversational"
                            st.session_state.chat_messages.append({
                                "role": "assistant",
                                "content": (
                                    f"Identified: **{profile.aadhaar.name}** ({profile.aadhaar.name_local})\n\n"
                                    f"- District: {profile.aadhaar.district}, {profile.aadhaar.state}\n"
                                    f"- Crops: {', '.join(profile.primary_crops)}\n"
                                    f"- Area: {profile.total_area:.2f} ha\n\n"
                                    f"I now have access to your soil health, insurance, subsidies, "
                                    f"and can give personalized weather advisories."
                                ),
                            })
                        else:
                            st.session_state.farmer_identified = False
                            st.session_state.farmer_info = None
                            st.warning("No farmer found for this number")
                    except Exception as exc:
                        st.error(f"Lookup failed: {exc}")
                st.rerun()

    with col2:
        if st.button("Clear", use_container_width=True):
            st.session_state.farmer_phone = ""
            st.session_state.farmer_identified = False
            st.session_state.farmer_info = None
            st.session_state.agent_mode = "generic"
            st.rerun()

    # Farmer profile card
    if st.session_state.farmer_identified and st.session_state.farmer_info:
        info = st.session_state.farmer_info
        st.divider()
        st.markdown(f"**{info['name']}**")
        st.markdown(f"*{info['name_local']}*")
        st.caption(f"{info['district']}, {info['state']}")
        st.caption(f"Crops: {', '.join(info['crops'])}")
        st.caption(f"Area: {info['area']:.2f} ha")

        lang_labels = {"ta": "Tamil", "ml": "Malayalam", "en": "English"}
        st.caption(f"Language: {lang_labels.get(info['language'], info['language'])}")

        # State badge
        st.markdown(f"**Mode:** `{st.session_state.agent_mode}`")

    st.divider()

    if st.button("🗑️ Clear conversation", use_container_width=True):
        st.session_state.chat_messages = [{
            "role": "assistant",
            "content": (
                "I'm your Weather AI assistant for Kerala and Tamil Nadu. "
                "I can check station health, run forecasts, show pipeline metrics, "
                "and explain the architecture."
            ),
        }]
        st.rerun()

    st.divider()
    st.markdown("**Quick prompts**")

    if st.session_state.farmer_identified:
        quick_prompts = [
            "What's the weather forecast for my area?",
            "Show me my soil health card",
            "What is my insurance status?",
            "Give me a personalized advisory",
        ]
    else:
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

    # Show available farmers for demo
    st.divider()
    st.markdown("**Demo farmers**")
    try:
        from src.dpi.simulator import get_registry
        registry = get_registry()
        for f in registry.list_farmers()[:6]:
            if st.button(f"{f['name']} ({f['phone'][-4:]})", key=f"farmer_{f['phone']}",
                         use_container_width=True):
                st.session_state.farmer_phone = f["phone"]
                st.rerun()
    except Exception:
        st.caption("Run the pipeline first to see demo farmers")

# ---------------------------------------------------------------------------
# Render conversation history
# ---------------------------------------------------------------------------
for msg in st.session_state.chat_messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# ---------------------------------------------------------------------------
# Handle input
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
                from streamlit_app.data_helpers import DB_PATH

                if st.session_state.agent_mode == "conversational":
                    from src.conversation import ConversationalAgent
                    agent = ConversationalAgent(config, db_path=DB_PATH)
                    # Identify the farmer in the agent
                    if st.session_state.farmer_phone:
                        asyncio.run(agent.identify(st.session_state.farmer_phone))
                    response = agent.chat(
                        user_input, history,
                        session_id=st.session_state.chat_session_id,
                        db_path=DB_PATH,
                    )
                else:
                    from src.nl_agent import NLAgent
                    agent = NLAgent(config)
                    response = agent.chat(
                        user_input, history,
                        session_id=st.session_state.chat_session_id,
                        db_path=DB_PATH,
                    )

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
