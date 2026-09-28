"""
ui/layout.py
=============
Global Page Configuration and Custom CSS Styling.

This module owns every visual styling decision for the IntellectaEngine
application. The design returns to the premium "Cosmic Deep Blue" aesthetic
with subtle violet and cyan accents, but carefully fixes contrast issues,
removes harsh whites, and ensures consistent glassmorphism.

Usage:
    from intellectaengine.ui.layout import apply_global_styles, render_header

    apply_global_styles()   # Call once at app startup
    render_header()         # Render the top banner
"""

from __future__ import annotations

import streamlit as st

from intellectaengine.config.settings import settings


def configure_page() -> None:
    """Set Streamlit page-level configuration."""
    st.set_page_config(
        page_title=settings.app_title,
        page_icon="🧠",
        layout="wide",
        initial_sidebar_state="expanded",
    )


def apply_global_styles() -> None:
    """Inject the complete custom CSS design system."""
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

    :root {
        /* Deep blue space base */
        --bg-deep:           #040814;
        --bg-card:           rgba(13, 17, 38, 0.65);
        --bg-input:          rgba(15, 23, 42, 0.85);
        --bg-sidebar:        rgba(6, 9, 20, 0.95);

        /* Accents */
        --accent-violet:     #8B5CF6;
        --accent-blue:       #3B82F6;
        --accent-cyan:       #06B6D4;

        /* Typography - No stark whites */
        --text-heading:      #E2E8F0;
        --text-body:         #CBD5E1;
        --text-muted:        #8492A6;

        /* Borders */
        --border-subtle:     rgba(139, 92, 246, 0.15);
        --border-medium:     rgba(139, 92, 246, 0.30);
        --border-focus:      #8B5CF6;

        --font-sans:         'Inter', sans-serif;
        --font-mono:         'JetBrains Mono', monospace;
    }

    /* Keyframes */
    @keyframes meshGradientShift {
        0%, 100% { background-position: 0% 50%; }
        50%      { background-position: 100% 50%; }
    }
    @keyframes orbFloat {
        0%, 100% { transform: translateY(0px) scale(1); }
        50%      { transform: translateY(-20px) scale(1.05); }
    }

    /* Base Reset */
    html, body, .stApp {
        font-family: var(--font-sans) !important;
        background-color: var(--bg-deep) !important;
        color: var(--text-body) !important;
    }

    /* Animated Cosmic Background */
    .stApp::before {
        content: '';
        position: fixed;
        inset: 0;
        background:
            radial-gradient(ellipse 600px 400px at 15% 15%, rgba(139, 92, 246, 0.08) 0%, transparent 70%),
            radial-gradient(ellipse 500px 500px at 85% 85%, rgba(59, 130, 246, 0.06) 0%, transparent 70%),
            radial-gradient(ellipse 400px 300px at 50% 50%, rgba(6, 182, 212, 0.04) 0%, transparent 70%);
        animation: meshGradientShift 20s ease-in-out infinite;
        background-size: 200% 200%;
        pointer-events: none;
        z-index: 0;
    }

    /* Text elements - ensuring consistency, removing harsh whites */
    h1, h2, h3, h4, h5, h6 {
        font-family: var(--font-sans) !important;
        color: var(--text-heading) !important;
        font-weight: 700 !important;
        letter-spacing: -0.015em;
    }

    p, li, span, label, .stMarkdown {
        color: var(--text-body) !important;
    }

    code, pre {
        font-family: var(--font-mono) !important;
        background: rgba(15, 23, 42, 0.8) !important;
        border: 1px solid var(--border-subtle) !important;
        color: #A5B4FC !important; /* Soft indigo for code */
    }

    /* Main Container */
    .main .block-container {
        padding: 2rem 3rem 4rem !important;
        max-width: 1050px !important;
    }

    /* Sidebar */
    [data-testid="stSidebar"] {
        background: var(--bg-sidebar) !important;
        border-right: 1px solid var(--border-subtle) !important;
        backdrop-filter: blur(24px) !important;
    }
    [data-testid="stSidebar"] h4 {
        color: var(--text-muted) !important;
        font-size: 0.75rem !important;
        text-transform: uppercase;
        border-bottom: 1px solid var(--border-subtle) !important;
        padding-bottom: 0.4rem !important;
    }

    /* Buttons */
    .stButton > button {
        background: rgba(30, 41, 59, 0.6) !important;
        color: var(--text-heading) !important;
        border: 1px solid var(--border-medium) !important;
        border-radius: 8px !important;
        font-weight: 500 !important;
        transition: all 0.2s ease !important;
    }
    .stButton > button:hover {
        background: rgba(139, 92, 246, 0.15) !important;
        border-color: var(--accent-violet) !important;
        box-shadow: 0 0 15px rgba(139, 92, 246, 0.15) !important;
    }
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, var(--accent-violet) 0%, var(--accent-blue) 100%) !important;
        color: #FFFFFF !important;
        border: none !important;
        box-shadow: 0 4px 15px rgba(139, 92, 246, 0.3) !important;
    }

    /* Inputs & Selects - Fix for harsh whites */
    .stTextInput > div > div > input,
    .stTextArea > div > div > textarea,
    .stSelectbox > div > div,
    .stMultiSelect > div > div {
        background: var(--bg-input) !important;
        border: 1px solid var(--border-medium) !important;
        color: var(--text-heading) !important;
        border-radius: 8px !important;
    }
    .stTextInput > div > div > input:focus,
    .stTextArea > div > div > textarea:focus,
    .stSelectbox > div > div:focus {
        border-color: var(--border-focus) !important;
        box-shadow: 0 0 0 2px rgba(139, 92, 246, 0.25) !important;
    }

    /* Chat Messages */
    [data-testid="stChatMessage"] {
        background: var(--bg-card) !important;
        border: 1px solid var(--border-subtle) !important;
        border-radius: 16px !important;
        padding: 1.2rem !important;
        margin-bottom: 1rem !important;
        backdrop-filter: blur(12px) !important;
    }
    [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
        background: rgba(139, 92, 246, 0.05) !important;
        border-left: 3px solid var(--accent-violet) !important;
    }
    [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) {
        background: rgba(59, 130, 246, 0.03) !important;
        border-left: 3px solid var(--accent-blue) !important;
    }

    /* Chat Input */
    [data-testid="stChatInput"] {
        background: var(--bg-input) !important;
        border: 1px solid var(--border-medium) !important;
        border-radius: 20px !important;
    }
    [data-testid="stChatInput"]:focus-within {
        border-color: var(--accent-violet) !important;
        box-shadow: 0 0 20px rgba(139, 92, 246, 0.15) !important;
    }
    [data-testid="stChatInput"] textarea {
        color: var(--text-heading) !important;
    }

    /* Cards, Metrics, Uploader */
    [data-testid="stMetric"], [data-testid="stExpander"] {
        background: var(--bg-card) !important;
        border: 1px solid var(--border-subtle) !important;
        border-radius: 12px !important;
    }
    [data-testid="stFileUploader"] {
        background: rgba(15, 23, 42, 0.5) !important;
        border: 2px dashed var(--border-medium) !important;
        border-radius: 12px !important;
    }

    hr {
        border-color: var(--border-subtle) !important;
        opacity: 0.5;
    }

    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    header[data-testid="stHeader"] { background: transparent !important; }
    </style>
    """, unsafe_allow_html=True)


def render_header() -> None:
    """Render the animated gradient hero header banner."""
    st.markdown(f"""
    <div style="
        background: linear-gradient(160deg, rgba(139,92,246,0.12) 0%, rgba(59,130,246,0.10) 50%, rgba(6,182,212,0.08) 100%);
        border: 1px solid rgba(139,92,246,0.25);
        border-radius: 20px;
        padding: 2rem 2.5rem;
        margin-bottom: 2rem;
        backdrop-filter: blur(24px);
        position: relative;
        overflow: hidden;
    ">
        <div style="
            position: absolute; top: -30px; right: -30px; width: 150px; height: 150px;
            background: radial-gradient(circle, rgba(139,92,246,0.15) 0%, transparent 70%);
            border-radius: 50%; animation: orbFloat 8s ease-in-out infinite; pointer-events: none;
        "></div>
        <div style="display: flex; align-items: center; gap: 1.2rem; position: relative; z-index: 1;">
            <div style="
                width: 60px; height: 60px;
                background: linear-gradient(135deg, rgba(139,92,246,0.2), rgba(59,130,246,0.15));
                border: 1px solid rgba(139,92,246,0.3);
                border-radius: 16px; display: flex; align-items: center; justify-content: center;
                font-size: 2rem; box-shadow: 0 0 25px rgba(139,92,246,0.15);
            ">🧠</div>
            <div>
                <h1 style="margin: 0; font-size: 2rem; font-weight: 800; background: linear-gradient(135deg, #E2E8F0 0%, #A78BFA 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; letter-spacing: -0.02em;">{settings.app_title}</h1>
                <p style="margin: 0.25rem 0 0; color: #94A3B8; font-size: 0.95rem;">{settings.app_subtitle}</p>
            </div>
        </div>
        <div style="display: flex; gap: 0.75rem; flex-wrap: wrap; margin-top: 1.25rem; position: relative; z-index: 1;">
            <span style="background: rgba(139,92,246,0.15); color: #C4B5FD; border: 1px solid rgba(139,92,246,0.3); border-radius: 8px; padding: 4px 12px; font-size: 0.75rem; font-weight: 600;">📄 Advanced RAG</span>
            <span style="background: rgba(59,130,246,0.15); color: #93C5FD; border: 1px solid rgba(59,130,246,0.3); border-radius: 8px; padding: 4px 12px; font-size: 0.75rem; font-weight: 600;">🗄️ SQL Intelligence</span>
            <span style="background: rgba(6,182,212,0.15); color: #67E8F9; border: 1px solid rgba(6,182,212,0.3); border-radius: 8px; padding: 4px 12px; font-size: 0.75rem; font-weight: 600;">🌐 Web Research</span>
            <span style="background: rgba(236,72,153,0.15); color: #F9A8D4; border: 1px solid rgba(236,72,153,0.3); border-radius: 8px; padding: 4px 12px; font-size: 0.75rem; font-weight: 600;">💬 Conversational AI</span>
        </div>
    </div>
    """, unsafe_allow_html=True)
