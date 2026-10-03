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

# Only static, application-owned strings are rendered as badge HTML.
_TOOL_BADGE_MAP = {
    "rag_document_search": '<span class="tool-badge">PDF retrieval</span>',
    "sql_database_query": '<span class="tool-badge">SQLite query</span>',
    "web_research": '<span class="tool-badge">Web research</span>',
    "general_chat": '<span class="tool-badge">Direct chat</span>',
    "chat_direct": '<span class="tool-badge">Direct chat</span>',
}

_STARTERS = (
    (
        "PDF documents",
        "Upload and process PDFs in Sources before asking.",
        "Summarize the key findings in my uploaded documents.",
    ),
    (
        "SQLite analysis",
        "Connect the Chinook sample database in Sources.",
        "Which three billing countries have the highest invoice totals?",
    ),
    (
        "Web research",
        "Choose Web research to search without an LLM.",
        "SQLite window functions documentation",
    ),
    (
        "Direct conversation",
        "Choose a provider and model in Model settings.",
        "Explain when retrieval-augmented generation is useful.",
    ),
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
        st.markdown(
            '<section class="ie-welcome"><div class="ie-eyebrow">A place to connect the dots</div>'
            '<h1>Your sources.<br><span class="ie-accent">One conversation.</span></h1>'
            "<p>Explore documents, query your data, and research the web in one workspace. "
            "Choose a source to get started, or let the agent find the right tool.</p></section>",
            unsafe_allow_html=True,
        )
        for row in range(2):
            columns = st.columns(2)
            for index, column in enumerate(columns):
                title, guidance, prompt = _STARTERS[row * 2 + index]
                with column, st.container(border=True, key=f"starter_{row}_{index}"):
                    st.markdown(f"### {title}")
                    st.caption(guidance)
                    st.button(
                        prompt,
                        key=f"prompt_{row}_{index}",
                        use_container_width=True,
                        on_click=ChatInterface._prefill_prompt,
                        args=(prompt,),
                        help="Add this example to the input. Edit it, then send when ready.",
                    )
        st.caption(
            "Examples fill the input only. Review your source and answer mode before sending."
        )

    @staticmethod
    def _prefill_prompt(prompt: str) -> None:
        st.session_state[K.KEY_CHAT_DRAFT] = prompt

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

        avatar = ":material/person:" if role == "user" else ":material/hub:"

        with st.chat_message(role, avatar=avatar):
            if role == "assistant" and tool and tool != "—":
                badge_html = _TOOL_BADGE_MAP.get(tool, "")
                if badge_html:
                    st.markdown(badge_html, unsafe_allow_html=True)
            st.markdown(content)
            if role == "assistant" and msg.get("sources"):
                with st.expander(f"Retrieved sources ({len(msg['sources'])})"):
                    st.caption(
                        "Context supplied to the model; these references do not verify every claim."
                    )
                    for source in msg["sources"]:
                        name = getattr(source, "source", None) or "Source metadata unavailable"
                        page = getattr(source, "page", None)
                        # Treat uploaded filenames as text, not Markdown links or HTML.
                        st.text(f"{name}{f' · page {page}' if page is not None else ''}")

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
        mode = st.session_state.get(K.KEY_AGENT_MODE, "auto")
        placeholders = {
            "auto": "Ask a question across your sources…",
            "rag": "Ask about your active PDFs…",
            "sql": "Ask about your connected database…",
            "web": "Search the public web…",
            "chat": "Message your selected model…",
        }
        placeholder = (
            placeholders[mode] if is_ready else "Choose a model in Model settings to begin."
        )

        user_query: str | None = st.chat_input(
            placeholder=placeholder,
            disabled=not is_ready,
            key=K.KEY_CHAT_DRAFT,
        )

        if not user_query:
            return

        # Immediately display the user message
        with st.chat_message("user", avatar=":material/person:"):
            st.markdown(user_query)

        # Invoke the router agent
        with st.chat_message("assistant", avatar=":material/hub:"):
            with st.spinner(
                "Choosing a tool and preparing a response…"
                if mode == "auto"
                else "Searching the web…"
                if mode == "web"
                else "Preparing a response…"
            ):
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
