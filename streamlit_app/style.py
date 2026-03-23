"""Shared CSS for the weather AI 2 dashboard — matches weather AI design language."""

import streamlit as st

CUSTOM_CSS = '''
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif;
    }

    .stApp { background-color: #faf8f5; }

    [data-testid="stSidebar"] {
        background-color: #1a1a1a !important;
    }
    [data-testid="stSidebar"] * { color: #e0dcd5 !important; }
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 { color: #ffffff !important; }
    [data-testid="stSidebar"] .stMetric label { color: #888 !important; }
    [data-testid="stSidebar"] .stMetric [data-testid="stMetricValue"] { color: #d4a019 !important; }
    [data-testid="stSidebar"] .stDivider { border-color: #333 !important; }
    [data-testid="stSidebar"] [data-testid="stMetric"] {
        background: rgba(255,255,255,0.05) !important;
        border: 1px solid #333 !important;
    }

    h1, h2, h3 {
        color: #1a1a1a !important;
        font-family: 'Inter', 'Segoe UI', system-ui, sans-serif !important;
    }
    h1 { font-weight: 700 !important; }
    h2, h3 { font-weight: 600 !important; }

    [data-testid="stMetric"] {
        background: #ffffff;
        border: 1px solid #e0dcd5;
        border-radius: 8px;
        padding: 16px;
    }
    [data-testid="stMetric"] label {
        color: #666 !important;
        text-transform: uppercase;
        font-size: 0.75rem !important;
        letter-spacing: 1px;
    }
    [data-testid="stMetric"] [data-testid="stMetricValue"] {
        color: #1a1a1a !important;
        font-weight: 700 !important;
    }

    .stButton > button {
        background-color: #d4a019 !important;
        color: #fff !important;
        border: none !important;
        border-radius: 4px !important;
        font-weight: 600 !important;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        transition: background-color 0.2s ease;
    }
    .stButton > button:hover { background-color: #b8880f !important; color: #fff !important; }
    .stButton > button:active, .stButton > button:focus { background-color: #a67a0d !important; }

    .stTabs [data-baseweb="tab-list"] { border-bottom: 1px solid #e0dcd5; }
    .stTabs [data-baseweb="tab"] { color: #666; font-weight: 500; }
    .stTabs [aria-selected="true"] {
        color: #d4a019 !important;
        border-bottom-color: #d4a019 !important;
        font-weight: 600;
    }

    hr { border-color: #e0dcd5 !important; }

    [data-testid="stSelectbox"] > div > div { border-color: #d0ccc5 !important; }
    .stTextInput > div > div > input { border-color: #d0ccc5 !important; }

    .streamlit-expanderHeader {
        background-color: #f0ede8 !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
    }

    .stDataFrame {
        border-radius: 8px;
        overflow: hidden;
        border: 1px solid #e0dcd5;
    }

    .stAlert { border-radius: 8px; }

    .stCaption, [data-testid="stCaptionContainer"] { color: #666 !important; }

    .section-header {
        font-size: 0.8rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 1.5px;
        color: #666;
        border-bottom: 2px solid #d4a019;
        padding-bottom: 6px;
        margin-bottom: 16px;
        display: inline-block;
    }

    [data-testid="stChatMessage"] {
        border: 1px solid #e0dcd5;
        border-radius: 8px;
        background: #ffffff;
    }
    .stChatInputContainer {
        border-color: #d0ccc5 !important;
    }
    .stChatInputContainer > div {
        border-color: #d0ccc5 !important;
        border-radius: 8px !important;
    }

    /* Pipeline diagram cards */
    .pipeline-card {
        background: #ffffff;
        border: 1px solid #e0dcd5;
        border-radius: 8px;
        padding: 14px 10px;
        text-align: center;
        min-height: 76px;
        transition: border-color 0.2s ease, box-shadow 0.2s ease;
        cursor: pointer;
    }
    .pipeline-card:hover {
        border-color: #d4a019;
        box-shadow: 0 2px 8px rgba(212,160,25,0.15);
    }
    .pipeline-card .card-title {
        font-weight: 600; color: #1a1a1a; font-size: 0.85rem;
    }
    .pipeline-card .card-stat {
        color: #888; font-size: 0.72rem; margin-top: 4px;
    }
    .pipeline-arrow {
        text-align: center; padding-top: 26px;
        color: #d4a019; font-size: 1.2rem; font-weight: 300;
    }

    /* De-emphasised System link */
    .system-link {
        font-size: 0.75rem; color: #888; text-decoration: none;
        letter-spacing: 0.5px;
    }
    .system-link:hover { color: #d4a019; }

    /* Chat toggle in sidebar */
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
    "heavy_rain":    "🌧️",
    "moderate_rain": "🌦️",
    "heat_stress":   "🌡️",
    "drought_risk":  "🌵",
    "frost_risk":    "❄️",
    "high_wind":     "💨",
    "foggy":         "🌫️",
    "clear":         "☀️",
}


STATUS_COLOR = {
    "ok": "#2a9d8f",
    "partial": "#f4a261",
    "failed": "#e63946",
    "running": "#1976D2",
}


def inject_css():
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
