"""
ui/chat_interface.py
=====================
Chat Display and Input Interface.

This module renders the full conversational UI: the message history, the
chat input box, tool invocation badges, source document references, and
developer debug panels. It bridges the user's text input with the
``ApplicationService`` orchestration layer and updates session state with results.

Responsibilities:
- Render historical messages with per-message tool attribution badges
- Capture new user input from ``st.chat_input``
- Build the ``AgentContext`` from current session state
- Invoke ``ApplicationService.run()`` and display the response
- Show source documents (when available) in collapsible popovers
- Display developer debug information when developer mode is on

Usage:
    from intellectaengine.ui.chat_interface import ChatInterface

    ChatInterface.render()
"""

from __future__ import annotations

import logging

import streamlit as st

from intellectaengine.core.application import ApplicationService
from intellectaengine.core.contracts import AgentContext, AgentResult, ErrorCode
from intellectaengine.ui.session_state import SessionStateManager

logger = logging.getLogger(__name__)

K = SessionStateManager  # Alias for brevity

# Map tool names to display badges HTML
_TOOL_BADGE_MAP: dict[str, str] = {
    "rag_document_search": '<span class="tool-badge tool-badge-rag">📄 RAG</span>',
    "sql_database_query": '<span class="tool-badge tool-badge-sql">🗄️ SQL</span>',
    "web_research": '<span class="tool-badge tool-badge-web">🌐 Web</span>',
    "general_chat": '<span class="tool-badge tool-badge-chat">💬 Chat</span>',
    "chat_direct": '<span class="tool-badge tool-badge-chat">💬 Chat</span>',
    "unknown": '<span class="tool-badge tool-badge-error">❓ Unknown</span>',
    "—": "",
}

# Welcome message shown before any conversation begins
_WELCOME_MESSAGE: str = (
    "👋 **Welcome to IntellectaEngine!**\n\n"
    "I'm your unified AI research assistant. Here's what I can do:\n\n"
    "- 📄 **Answer questions from your PDFs** — Upload documents in the sidebar, "
    "then ask anything about their contents.\n"
    "- 🗄️ **Query SQL databases** — Connect a database and ask questions in plain English.\n"
    "- 🌐 **Search the web** — Ask about recent events or live data.\n"
    "- 💬 **General conversation** — Explain concepts, write code, brainstorm ideas.\n\n"
    "*The router agent automatically selects the best tool for each question.*"
)


class ChatInterface:
    """
    Stateless class that renders the complete chat UI and handles message
    processing via the ``ApplicationService``.

    Call ``ChatInterface.render()`` once in the main panel of the app.

    Example:
        >>> ChatInterface.render()
    """

    @classmethod
    def render(cls) -> None:
        """
        Render the full chat interface: welcome message, history, and input box.

        This is the main entry point called from ``app.py``. It:
        1. Displays the welcome message if no history exists.
        2. Renders all historical messages with tool badges.
        3. Renders the chat input box.
        4. On new input, invokes the router agent and displays the result.

        Example:
            >>> ChatInterface.render()
        """
        messages: list[dict] = st.session_state.get(K.KEY_CHAT_MESSAGES, [])

        # Show welcome screen
        if not messages:
            cls._render_welcome()

        # Render existing conversation history
        for msg in messages:
            cls._render_message(msg)

        # Input box — always at the bottom
        cls._render_input_box()

    # ------------------------------------------------------------------
    # Sub-renderers
    # ------------------------------------------------------------------

    @staticmethod
    def _render_welcome() -> None:
        """Render the welcome info panel when no messages exist."""
        with st.chat_message("assistant", avatar="🧠"):
            st.markdown(_WELCOME_MESSAGE)

    @staticmethod
    def _render_message(msg: dict) -> None:
        """
        Render a single message from the chat history.

        Args:
            msg: Dictionary with keys ``'role'``, ``'content'``, and
                 optionally ``'tool'``.
        """
        role: str = msg.get("role", "assistant")
        content: str = msg.get("content", "")
        tool: str = msg.get("tool", "—")

        avatar = "👤" if role == "user" else "🧠"

        with st.chat_message(role, avatar=avatar):
            if role == "assistant" and tool and tool != "—":
                badge_html = _TOOL_BADGE_MAP.get(tool, "")
                if badge_html:
                    st.markdown(badge_html, unsafe_allow_html=True)
            st.markdown(content)
            if role == "assistant" and msg.get("sources"):
                st.caption("Retrieved sources (context locations; not claim verification):")
                for source in msg["sources"]:
                    name = getattr(source, "source", None) or "Source metadata unavailable"
                    page = getattr(source, "page", None)
                    st.caption(f"• {name}{f' (p. {page})' if page is not None else ''}")

    @classmethod
    def _render_input_box(cls) -> None:
        """
        Render the chat input field and handle new user submissions.

        When the user submits a query, this method:
        1. Displays the pending user message.
        2. Builds the ``AgentContext`` from session state.
        3. Invokes ``ApplicationService.run()`` (with spinner).
        4. Commits the complete turn to visible and model history.
        5. Updates ``KEY_ACTIVE_TOOL`` in session state.
        6. Forces a ``st.rerun()`` to refresh the full message list.
        """
        provider = st.session_state.get(K.KEY_LLM_PROVIDER, "gemini")
        model = st.session_state.get(K.KEY_LLM_MODEL)

        is_ready = bool(model) or st.session_state.get(K.KEY_AGENT_MODE) == "web"
        placeholder = (
            "⚡ Ask anything — the agent will choose the right tool…"
            if is_ready
            else "⚠️ Select an LLM provider and model in the sidebar first."
        )

        user_query: str | None = st.chat_input(
            placeholder=placeholder,
            disabled=not is_ready,
        )

        if not user_query:
            return

        # Immediately display the user message
        with st.chat_message("user", avatar="👤"):
            st.markdown(user_query)

        # Invoke the router agent
        with st.chat_message("assistant", avatar="🧠"):
            with st.spinner("🔄 Routing query to the best tool…"):
                try:
                    context = cls._build_agent_context()
                    agent_mode = st.session_state.get(K.KEY_AGENT_MODE, "auto")
                    result = ApplicationService.run(
                        query=user_query,
                        provider=provider,
                        model=model,
                        context=context,
                        mode=agent_mode,
                    )

                except Exception:
                    result = AgentResult.failure(ErrorCode.EXECUTION_FAILURE)

                # The only persistence boundary: final replies and displayed errors.
                K.complete_turn(user_query, result.answer, result.tool_used, result.sources)
                badge_html = _TOOL_BADGE_MAP.get(result.tool_used, "")
                if badge_html:
                    st.markdown(badge_html, unsafe_allow_html=True)
                st.markdown(result.answer)

                if st.session_state.get(K.KEY_DEVELOPER_MODE) and result.error:
                    st.caption(f"Failure code: {result.error.value}")

        st.rerun()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_agent_context() -> AgentContext:
        """
        Construct an ``AgentContext`` from the current session state.

        Returns:
            ``AgentContext`` populated with vector store, DB URI,
            PDF names, and session ID.
        """
        return AgentContext(
            session_id=st.session_state[K.KEY_SESSION_ID],
            memory=st.session_state[K.KEY_MEMORY],
            vector_store=st.session_state.get(K.KEY_VECTOR_STORE),
            db_uri=(
                st.session_state.get(K.KEY_DB_URI, "")
                if st.session_state.get(K.KEY_DB_CONNECTED, False)
                else None
            ),
            pdf_names=st.session_state.get(K.KEY_PDF_NAMES, []),
        )
