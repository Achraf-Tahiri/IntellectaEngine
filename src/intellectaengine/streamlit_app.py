"""
streamlit_app.py
================
IntellectaEngine — Streamlit Application Entry Point.

This file is the single entry point for the application. Its sole
responsibility is to wire together the UI layer components in the
correct order. No business logic lives here.

Execution order:
    1. ``configure_page()``   — Must be the very first Streamlit call.
    2. ``apply_global_styles()`` — Inject CSS design system.
    3. ``SessionStateManager.initialise()`` — Bootstrap session state.
    4. ``SidebarRenderer.render()`` — Render full sidebar configuration.
    5. ``render_header()``    — Render the animated hero banner.
    6. ``ChatInterface.render()`` — Render the conversational UI.

Run:
    intellectaengine [Streamlit options]
"""

import os
from pathlib import Path
import sys


def launch() -> None:
    """Replace this process with Streamlit, forwarding arguments unchanged."""
    os.execv(
        sys.executable,
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(Path(__file__).with_name("streamlit_app.py")),
            *sys.argv[1:],
        ],
    )


def main() -> None:
    """
    Application bootstrap and main render loop.

    This function configures the Streamlit page, applies the global design
    system, initialises session state, renders the sidebar and the chat
    interface. It is called once per browser session refresh.
    """
    import streamlit as st

    from intellectaengine.ui.layout import apply_global_styles, configure_page, render_header
    from intellectaengine.ui.session_state import SessionStateManager
    from intellectaengine.ui.sidebar import SidebarRenderer
    from intellectaengine.ui.chat_interface import ChatInterface

    # Streamlit 1.64 guards namespace-path inspection of torch.classes. No
    # global PyTorch mutation is needed (see the watcher regression test).
    # Step 1: Streamlit page config — MUST be first
    configure_page()

    # Step 2: Inject the full CSS design system
    apply_global_styles()

    # Step 3: Idempotently initialise all session state keys
    SessionStateManager.initialise()

    # Step 4: Render the sidebar (provider config, uploads, DB, utilities)
    with st.sidebar:
        SidebarRenderer.render()

    # Step 5: Render the animated hero header
    render_header()

    # Step 6: Render the full conversational chat interface
    ChatInterface.render()


if __name__ == "__main__":
    main()
