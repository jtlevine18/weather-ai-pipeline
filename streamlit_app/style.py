"""Shared CSS for the weather AI 2 dashboard — warm editorial design language."""

import streamlit as st

CUSTOM_CSS = '''
<style>
    @import url('https://fonts.googleapis.com/css2?family=Source+Serif+4:ital,opsz,wght@0,8..60,300;0,8..60,400;0,8..60,600;0,8..60,700;1,8..60,400&family=DM+Sans:wght@400;500;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'DM Sans', 'Segoe UI', system-ui, sans-serif;
    }

    .stApp {
        background-color: #faf8f5;
        background-image:
            radial-gradient(ellipse 80% 60% at 20% 0%, rgba(212,160,25,0.04), transparent),
            radial-gradient(ellipse 60% 50% at 80% 100%, rgba(46,125,50,0.03), transparent);
    }

    /* --- Sidebar --- */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1a1a1a 0%, #222018 100%) !important;
    }
    [data-testid="stSidebar"] * { color: #e0dcd5 !important; }
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 { color: #ffffff !important; }
    [data-testid="stSidebar"] .stMetric label { color: #999 !important; }
    [data-testid="stSidebar"] .stMetric [data-testid="stMetricValue"] { color: #d4a019 !important; }
    [data-testid="stSidebar"] .stDivider { border-color: #333 !important; }
    [data-testid="stSidebar"] [data-testid="stMetric"] {
        background: rgba(255,255,255,0.04) !important;
        border: 1px solid rgba(255,255,255,0.08) !important;
    }

    /* --- Typography --- */
    h1, h2, h3 {
        color: #1a1a1a !important;
        font-family: 'Source Serif 4', Georgia, serif !important;
    }
    h1 { font-weight: 700 !important; }
    h2 { font-weight: 600 !important; }
    h3 { font-weight: 600 !important; }

    /* --- Metrics --- */
    [data-testid="stMetric"] {
        background: #ffffff;
        border: 1px solid #e0dcd5;
        border-radius: 10px;
        padding: 16px;
    }
    [data-testid="stMetric"] label {
        color: #888 !important;
        text-transform: uppercase;
        font-size: 0.72rem !important;
        letter-spacing: 1.2px;
        font-family: 'DM Sans', sans-serif !important;
    }
    [data-testid="stMetric"] [data-testid="stMetricValue"] {
        color: #1a1a1a !important;
        font-weight: 700 !important;
        font-family: 'Source Serif 4', Georgia, serif !important;
    }

    /* --- Buttons --- */
    .stButton > button {
        background-color: #d4a019 !important;
        color: #fff !important;
        border: none !important;
        border-radius: 6px !important;
        font-weight: 600 !important;
        font-family: 'DM Sans', sans-serif !important;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        font-size: 0.78rem !important;
        transition: all 0.25s ease;
    }
    .stButton > button:hover {
        background-color: #b8880f !important;
        color: #fff !important;
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(212,160,25,0.25);
    }
    .stButton > button:active, .stButton > button:focus {
        background-color: #a67a0d !important;
        transform: translateY(0);
    }

    /* --- Tabs --- */
    .stTabs [data-baseweb="tab-list"] { border-bottom: 1px solid #e0dcd5; }
    .stTabs [data-baseweb="tab"] { color: #888; font-weight: 500; }
    .stTabs [aria-selected="true"] {
        color: #d4a019 !important;
        border-bottom-color: #d4a019 !important;
        font-weight: 600;
    }

    hr { border-color: #e0dcd5 !important; }

    [data-testid="stSelectbox"] > div > div { border-color: #d0ccc5 !important; }
    .stTextInput > div > div > input { border-color: #d0ccc5 !important; }

    .streamlit-expanderHeader {
        background-color: #f5f2ed !important;
        border-radius: 10px !important;
        font-weight: 600 !important;
    }

    .stDataFrame {
        border-radius: 10px;
        overflow: hidden;
        border: 1px solid #e0dcd5;
    }

    .stAlert { border-radius: 10px; }

    .stCaption, [data-testid="stCaptionContainer"] { color: #888 !important; }

    /* --- Section headers --- */
    .section-header {
        font-size: 0.78rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 1.5px;
        color: #888;
        border-bottom: 2px solid #d4a019;
        padding-bottom: 6px;
        margin-bottom: 16px;
        display: inline-block;
        font-family: 'DM Sans', sans-serif;
    }

    /* --- Chat --- */
    [data-testid="stChatMessage"] {
        border: 1px solid #e0dcd5;
        border-radius: 10px;
        background: #ffffff;
    }
    .stChatInputContainer { border-color: #d0ccc5 !important; }
    .stChatInputContainer > div {
        border-color: #d0ccc5 !important;
        border-radius: 10px !important;
    }

    /* === HOME PAGE === */

    /* Hero */
    .hero-section {
        text-align: center;
        padding: 28px 20px 12px;
    }
    .hero-section h1 {
        font-family: 'Source Serif 4', Georgia, serif !important;
        font-size: 2.4rem !important;
        font-weight: 700 !important;
        color: #1a1a1a !important;
        letter-spacing: -1px;
        margin: 0 !important;
        line-height: 1.1;
    }
    .hero-accent {
        background: linear-gradient(135deg, #d4a019, #b8880f);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }
    .hero-subtitle {
        color: #666;
        font-size: 1rem;
        line-height: 1.65;
        margin: 10px auto 0;
        max-width: 600px;
        font-family: 'DM Sans', sans-serif;
    }

    /* Clickable stage cards */
    .stage-link {
        flex: 1;
        display: flex;
        flex-direction: column;
        background: #fff;
        border: 1px solid #e0dcd5;
        border-radius: 14px;
        padding: 22px 20px 16px;
        position: relative;
        overflow: hidden;
        text-decoration: none !important;
        color: inherit !important;
        cursor: pointer;
        transition: all 0.25s cubic-bezier(0.25, 0.46, 0.45, 0.94);
        font-family: 'DM Sans', sans-serif;
    }
    .stage-link:hover {
        border-color: #ccc8c0;
        box-shadow: 0 8px 28px rgba(0,0,0,0.06), 0 2px 8px rgba(0,0,0,0.03);
        transform: translateY(-3px);
        text-decoration: none !important;
        color: inherit !important;
    }
    .stage-link:visited { color: inherit !important; text-decoration: none !important; }
    .stage-link:active { transform: translateY(-1px); }

    /* --- System link --- */
    .system-link { font-size: 0.75rem; color: #888; text-decoration: none; letter-spacing: 0.5px; }
    .system-link:hover { color: #d4a019; }

    /* --- Chat toggle --- */
    .chat-toggle-btn {
        background: transparent !important;
        border: 1px solid #444 !important;
        color: #d4a019 !important;
        font-size: 0.8rem !important;
        text-transform: none !important;
        letter-spacing: 0 !important;
        font-weight: 500 !important;
        width: 100%;
    }
    .chat-toggle-btn:hover {
        background: rgba(212,160,25,0.1) !important;
        border-color: #d4a019 !important;
    }
</style>
'''

# Condition display helpers
CONDITION_COLOR = {
    "heavy_rain":    "#1565C0",
    "moderate_rain": "#1976D2",
    "heat_stress":   "#C62828",
    "drought_risk":  "#E65100",
    "frost_risk":    "#0277BD",
    "high_wind":     "#455A64",
    "foggy":         "#546E7A",
    "clear":         "#2E7D32",
}

CONDITION_EMOJI = {
    "heavy_rain":    "\U0001f327\ufe0f",
    "moderate_rain": "\U0001f326\ufe0f",
    "heat_stress":   "\U0001f321\ufe0f",
    "drought_risk":  "\U0001f335",
    "frost_risk":    "\u2744\ufe0f",
    "high_wind":     "\U0001f4a8",
    "foggy":         "\U0001f32b\ufe0f",
    "clear":         "\u2600\ufe0f",
}


STATUS_COLOR = {
    "ok": "#2a9d8f",
    "partial": "#f4a261",
    "failed": "#e63946",
    "running": "#1976D2",
}


def inject_css():
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# Shared sidebar nav hidden CSS + explicit page links
_SIDEBAR_NAV_CSS = """
<style>
    [data-testid="stSidebarNav"] { display: none !important; }
    nav[data-testid="stSidebarNav"] { display: none !important; }
    [data-testid="stSidebar"] ul[data-testid="stSidebarNavItems"] { display: none !important; }
</style>
"""


def inject_sidebar_nav():
    """Hide auto sidebar nav and render our own. Call on every page after inject_css()."""
    st.markdown(_SIDEBAR_NAV_CSS, unsafe_allow_html=True)
    with st.sidebar:
        st.page_link("app.py", label="Home", icon="🏠")
        st.page_link("pages/1_Data.py", label="Data", icon="📡")
        st.page_link("pages/2_Forecasts.py", label="Forecasts", icon="🌦")
        st.page_link("pages/3_Advisories.py", label="Advisories", icon="🌾")
        st.page_link("pages/_System.py", label="System", icon="⚙")
