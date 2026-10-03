"""Page layout and restrained, offline-friendly workspace styling."""

from __future__ import annotations

from html import escape

import streamlit as st

from intellectaengine.config.settings import settings
from intellectaengine.ui.session_state import SessionStateManager as K

MODE_LABELS = {
    "auto": "Auto route",
    "rag": "PDF documents",
    "sql": "SQLite database",
    "web": "Web research",
    "chat": "Direct chat",
}


def configure_page() -> None:
    st.set_page_config(
        page_title=settings.app_title,
        page_icon=":material/hub:",
        layout="wide",
        initial_sidebar_state="auto",
    )


def apply_global_styles() -> None:
    """Keep widget behavior native; style public test IDs and our own classes."""
    st.markdown(
        """
    <style>
    :root {
        --ie-bg: #0c111b;
        --ie-panel: #111a28;
        --ie-border: #293548;
        --ie-text: #e7edf7;
        --ie-muted: #a4b1c5;
        --ie-blue: #86b4ff;
    }
    .stApp { background: var(--ie-bg); }
    [data-testid="stMainBlockContainer"] {
        max-width: 1120px; padding: 4.5rem 3rem 3rem;
    }
    [data-testid="stSidebar"] {
        background: #101722; border-right: 1px solid var(--ie-border);
    }
    [data-testid="stSidebarUserContent"] { padding-top: 1.2rem; }
    [data-testid="stHeader"] { background: var(--ie-bg); }
    h1, h2, h3 { letter-spacing: -0.035em; }
    [data-testid="stCaptionContainer"] p { color: var(--ie-muted); }
    .ie-brand { display: flex; align-items: center; gap: 12px; margin-bottom: 1.5rem; }
    .ie-monogram {
        display: grid; place-items: center; width: 38px; height: 38px;
        border-radius: 10px; background: #1c355a; border: 1px solid #3c6196;
        color: #bcd5ff; font-size: 15px; font-weight: 750; letter-spacing: -1px;
    }
    .ie-brand strong { color: var(--ie-text); font-size: 1.05rem; }
    .ie-brand small { display: block; color: var(--ie-muted); font-size: .75rem; margin-top: 2px; }
    .ie-eyebrow { color: var(--ie-blue); font-size: .72rem; font-weight: 650;
        letter-spacing: .12em; text-transform: uppercase; margin: 0 0 .7rem; }
    .ie-topbar { display: flex; align-items: center; justify-content: space-between;
        gap: 1rem; padding-bottom: 1rem; border-bottom: 1px solid var(--ie-border); }
    .ie-topbar strong { font-size: .9rem; color: var(--ie-text); }
    .ie-topbar span { color: var(--ie-muted); font-size: .78rem; }
    .ie-status-row { display: flex; flex-wrap: wrap; gap: .6rem; margin: .9rem 0 1.6rem; }
    .ie-status { padding: .3rem .65rem; border: 1px solid var(--ie-border);
        border-radius: 6px; color: var(--ie-muted); font-size: .75rem; }
    .ie-status.active { color: #addacb; border-color: #31564c; background: #142b27; }
    .ie-status.setup { color: #edc98a; border-color: #624e31; background: #282319; }
    .ie-welcome { padding: 1.7rem 0 1.6rem; }
    .ie-welcome h1 { font-size: clamp(2rem, 4vw, 3.1rem); font-weight: 650;
        line-height: 1.12; margin: 0 0 1rem; padding: 0; color: var(--ie-text); }
    .ie-welcome .ie-accent { color: var(--ie-blue); }
    .ie-welcome p { color: var(--ie-muted); max-width: 540px; line-height: 1.65; margin: 0; }
    [class*="st-key-starter_"] { background: var(--ie-panel); border-radius: 12px; }
    [class*="st-key-starter_"] h3 { font-size: 1rem; letter-spacing: -.015em; padding-top: .1rem; }
    [class*="st-key-starter_"] [data-testid="stCaptionContainer"] p { min-height: 2.7rem; }
    [data-testid="stButton"] button { border-radius: 8px; min-height: 2.5rem; }
    [data-testid="stButton"] button:hover { border-color: #86b4ff; }
    [data-testid="stButton"] button:focus-visible { outline: 2px solid #86b4ff; outline-offset: 3px; }
    [data-testid="stChatMessage"] { background: var(--ie-panel); border: 1px solid var(--ie-border);
        border-radius: 12px; padding: 1.25rem; margin-bottom: .75rem; }
    [data-testid="stChatMessage"]:has([aria-label="Chat message from user"]) {
        background: transparent; border-color: transparent;
    }
    [data-testid="stChatMessage"] p, [data-testid="stChatMessage"] li { line-height: 1.7; }
    [data-testid="stChatInput"] { border-radius: 12px; border: 1px solid #3c506e; }
    [data-testid="stChatInput"]:focus-within { border-color: #86b4ff; }
    .tool-badge { display: inline-block; color: var(--ie-blue); border: 1px solid #34527d;
        background: #17273e; border-radius: 5px; padding: 2px 8px; font-size: .72rem; margin-bottom: .6rem; }
    @media (max-width: 768px) {
        [data-testid="stMainBlockContainer"] { padding: 4.5rem 1.1rem 2rem; }
        .ie-welcome { padding-top: .7rem; }
        .ie-topbar { align-items: flex-start; }
        .ie-topbar span { text-align: right; }
        [class*="st-key-starter_"] [data-testid="stCaptionContainer"] p { min-height: 0; }
    }
    </style>
    """,
        unsafe_allow_html=True,
    )


def render_header() -> None:
    """Show only session-derived status, never assumed service health."""
    provider = st.session_state[K.KEY_LLM_PROVIDER]
    mode = st.session_state[K.KEY_AGENT_MODE]
    model = st.session_state[K.KEY_LLM_MODEL]
    credentials = {
        "gemini": settings.google_api_key,
        "groq": settings.groq_api_key,
        "openai": settings.openai_api_key,
    }
    setup_needed = not model or (provider in credentials and not credentials[provider])
    if mode == "web":
        model_status, status_class = "Web mode · no LLM required", ""
    elif setup_needed:
        model_status, status_class = "Model setup required", "setup"
    else:
        model_status, status_class = f"{provider.capitalize()} · configured", ""
    has_docs = st.session_state[K.KEY_VECTOR_STORE] is not None
    doc_count = len(st.session_state[K.KEY_PDF_NAMES]) if has_docs else 0
    has_db = st.session_state[K.KEY_DB_CONNECTED]
    docs = f"PDFs · {doc_count} active" if has_docs else "PDFs · none added"
    database = "SQLite · connected" if has_db else "SQLite · not connected"
    st.markdown(
        f"""
    <div class="ie-topbar"><strong>Research workspace</strong><span>PDFs / SQLite / Web</span></div>
    <div class="ie-status-row" aria-label="Workspace status">
        <span class="ie-status">{escape(MODE_LABELS[mode])}</span>
        <span class="ie-status {"active" if has_docs else ""}">{docs}</span>
        <span class="ie-status {"active" if has_db else ""}">{database}</span>
        <span class="ie-status {status_class}">{escape(model_status)}</span>
    </div>
    """,
        unsafe_allow_html=True,
    )
