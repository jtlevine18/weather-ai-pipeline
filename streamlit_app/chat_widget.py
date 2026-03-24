"""Floating chat widget — renders as a sidebar toggle on any page."""

import asyncio
import os
import sys
import uuid

import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def init_chat_state():
    """Ensure chat session state exists."""
    if "chat_session_id" not in st.session_state:
        st.session_state.chat_session_id = str(uuid.uuid4())
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = [{
            "role": "assistant",
            "content": (
                "I'm your Weather AI assistant for Kerala and Tamil Nadu. "
                "I can check station health, run forecasts, show pipeline metrics, "
                "and explain the architecture. Enter a phone number to access "
                "personalized farmer services."
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
    if "chat_open" not in st.session_state:
        st.session_state.chat_open = False


def render_chat_toggle():
    """Render a small chat toggle button in the sidebar. Call on every page."""
    init_chat_state()
    with st.sidebar:
        st.markdown("---")
        label = "Close Chat" if st.session_state.chat_open else "Chat"
        if st.button(label, key="_chat_toggle", width="stretch"):
            st.session_state.chat_open = not st.session_state.chat_open
            st.rerun()

        if st.session_state.chat_open:
            _render_chat_panel()


def _render_chat_panel():
    """Render the full chat UI inside the sidebar."""
    st.markdown("---")

    # Farmer identity
    st.markdown("**Farmer Identity**")
    phone_input = st.text_input("Phone number", value=st.session_state.farmer_phone,
                                placeholder="+919876543210", key="_chat_phone")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Look up", key="_chat_lookup", width="stretch"):
            if phone_input.strip():
                st.session_state.farmer_phone = phone_input.strip()
                try:
                    from src.dpi.simulator import get_registry
                    profile = get_registry().lookup_by_phone(phone_input.strip())
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
                                f"Identified: **{profile.aadhaar.name}** "
                                f"({profile.aadhaar.name_local})\n\n"
                                f"- District: {profile.aadhaar.district}, {profile.aadhaar.state}\n"
                                f"- Crops: {', '.join(profile.primary_crops)}\n"
                                f"- Area: {profile.total_area:.2f} ha"
                            ),
                        })
                    else:
                        st.warning("No farmer found")
                except Exception as exc:
                    st.error(str(exc))
                st.rerun()
    with c2:
        if st.button("Clear", key="_chat_clear", width="stretch"):
            st.session_state.farmer_phone = ""
            st.session_state.farmer_identified = False
            st.session_state.farmer_info = None
            st.session_state.agent_mode = "generic"
            st.rerun()

    # Farmer profile card
    if st.session_state.farmer_identified and st.session_state.farmer_info:
        info = st.session_state.farmer_info
        st.caption(f"**{info['name']}** · {info['district']}, {info['state']}")
        st.caption(f"Crops: {', '.join(info['crops'])} · {info['area']:.1f} ha")

    st.markdown("---")

    # Demo farmers
    with st.expander("Demo farmers"):
        try:
            from src.dpi.simulator import get_registry
            for f in get_registry().list_farmers()[:6]:
                if st.button(f"{f['name']} ({f['phone'][-4:]})",
                             key=f"cw_{f['phone']}", width="stretch"):
                    st.session_state.farmer_phone = f["phone"]
                    st.rerun()
        except Exception:
            st.caption("Run the pipeline first")

    st.markdown("---")

    # Conversation history (compact)
    for msg in st.session_state.chat_messages[-6:]:
        role_label = "You" if msg["role"] == "user" else "AI"
        text = msg["content"][:200]
        if msg["role"] == "user":
            st.markdown(f"**{role_label}:** {text}")
        else:
            st.caption(f"{role_label}: {text}")

    # Chat input
    user_input = st.text_input("Ask something...", key="_chat_input",
                               label_visibility="collapsed")
    if st.button("Send", key="_chat_send", width="stretch") and user_input:
        st.session_state.chat_messages.append({"role": "user", "content": user_input})
        try:
            from config import get_config
            config = get_config()
            history = [
                {"role": m["role"], "content": m["content"]}
                for m in st.session_state.chat_messages[:-1]
            ]
            from streamlit_app.data_helpers import DB_PATH

            if st.session_state.agent_mode == "conversational":
                from src.conversation import ConversationalAgent
                agent = ConversationalAgent(config, db_path=DB_PATH)
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
            st.session_state.chat_messages.append(
                {"role": "assistant", "content": response}
            )
        except Exception as exc:
            st.session_state.chat_messages.append(
                {"role": "assistant", "content": f"Error: {exc}"}
            )
        st.rerun()

    if st.button("Clear conversation", key="_chat_clear_conv", width="stretch"):
        st.session_state.chat_messages = [{
            "role": "assistant",
            "content": "Chat cleared. How can I help?",
        }]
        st.rerun()
