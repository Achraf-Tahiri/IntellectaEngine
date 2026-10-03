"""
ui/sidebar.py
==============
Sidebar Controls and Configuration Renderer.

This module renders all content within the Streamlit sidebar:
- LLM provider + model selection
- Embedding provider selection
- PDF upload and processing
- SQL database connection
- Agent routing mode selector
- Utility actions (reset, clear chat, undo)

The sidebar is the configuration hub — it collects all runtime parameters
and updates ``st.session_state`` so the main panel and router agent can
read them. No business logic is executed here; the sidebar only collects
settings and triggers connectors to build resources (vector stores, DB
connections) that are stored in session state.

Usage:
    from intellectaengine.ui.sidebar import SidebarRenderer

    with st.sidebar:
        SidebarRenderer.render()
"""

from __future__ import annotations

import logging

import streamlit as st

from intellectaengine.config.settings import settings
from intellectaengine.connectors.database_connector import DatabaseConnector
from intellectaengine.core.document_ingestion import DocumentIngestionService
from intellectaengine.core.embedding_factory import EmbeddingFactory
from intellectaengine.core.contracts import AgentResult, ApplicationError, ErrorCode
from intellectaengine.core.llm_factory import LLMFactory
from intellectaengine.ui.session_state import SessionStateManager
from intellectaengine.ui.layout import MODE_LABELS

logger = logging.getLogger(__name__)

K = SessionStateManager  # Alias for brevity


class SidebarRenderer:
    """
    Renders all sidebar UI components and handles the side-effects of
    user interactions (e.g., uploading PDFs, connecting to databases).

    All methods are class-level and stateless. Session state is accessed
    and mutated via ``SessionStateManager`` to maintain the single-source-
    of-truth principle.

    Example:
        >>> with st.sidebar:
        ...     SidebarRenderer.render()
    """

    @classmethod
    def render(cls) -> None:
        """
        Render the complete sidebar content in logical section order.

        Sources and model settings stay mounted inside native expanders, so
        collapsing a panel does not discard its widget state.

        Example:
            >>> with st.sidebar:
            ...     SidebarRenderer.render()
        """
        cls._render_branding()
        cls._render_agent_mode_section()
        st.markdown("#### Sources")
        with st.expander("PDF documents", icon=":material/description:"):
            cls._render_pdf_section()
        with st.expander("SQLite database", icon=":material/database:"):
            cls._render_sql_section()
        with st.expander("Model settings", icon=":material/tune:"):
            cls._render_llm_section()
        st.divider()
        cls._render_utilities_section()
        with st.expander("Session details", icon=":material/info:"):
            cls._render_status_metrics()

    @staticmethod
    def _render_branding() -> None:
        st.markdown(
            '<div class="ie-brand"><div class="ie-monogram" aria-hidden="true">ie</div>'
            "<div><strong>IntellectaEngine</strong><small>Multi-source AI assistant</small></div></div>",
            unsafe_allow_html=True,
        )

    @staticmethod
    def _render_llm_section() -> None:
        """Render LLM provider, model, and embedding provider selectors."""

        # --- Provider ---
        provider = st.selectbox(
            "LLM provider",
            options=LLMFactory.list_providers(),
            key=K.KEY_LLM_PROVIDER,
            on_change=K.provider_changed,
            help="Select the AI provider powering all reasoning.",
        )

        # --- Model ---
        st.text_input(
            "Model",
            key=K.KEY_LLM_MODEL,
            help="Use the configured default or enter a model identifier available from this provider.",
        )

        # API key validation hint
        if provider == "gemini" and not settings.google_api_key:
            st.warning("Set GOOGLE_API_KEY in your environment or .env, then restart the app.")
        elif provider == "groq" and not settings.groq_api_key:
            st.warning("Set GROQ_API_KEY in your environment or .env, then restart the app.")
        elif provider == "openai" and not settings.openai_api_key:
            st.warning("Set OPENAI_API_KEY in your environment or .env, then restart the app.")
        elif provider == "ollama":
            st.info(
                "Ollama uses your configured server. Availability is checked on request.",
                icon="ℹ️",
            )

        # --- Embedding provider ---
        st.selectbox(
            "Embedding provider",
            options=EmbeddingFactory.list_providers(),
            key=K.KEY_EMBEDDING_PROVIDER,
            help=(
                "Embedding model used to vectorise PDF content. "
                "HuggingFace runs locally — no API key required."
            ),
        )

    @staticmethod
    def _render_agent_mode_section() -> None:
        """Render the agent routing mode selector."""
        st.selectbox(
            "Answer mode",
            options=list(MODE_LABELS),
            format_func=MODE_LABELS.get,
            key=K.KEY_AGENT_MODE,
            help="Auto route lets the agent choose a tool. Other modes use the selected tool directly.",
        )
        mode = st.session_state[K.KEY_AGENT_MODE]
        hints = {
            "auto": "The agent chooses a tool for each question.",
            "rag": "Answers from your active PDFs. Add documents below.",
            "sql": "Ask a connected SQLite database in plain language.",
            "web": "Search public web evidence. No LLM required.",
            "chat": "Talk directly with your selected model.",
        }
        st.caption(hints[mode])

    @classmethod
    def _render_pdf_section(cls) -> None:
        """Render PDF file uploader and processing controls."""

        embedding_provider = st.session_state.get(K.KEY_EMBEDDING_PROVIDER, "huggingface")
        model_selected = st.session_state.get(K.KEY_LLM_MODEL)

        uploader_key = st.session_state.get(K.KEY_UPLOADER_KEY, 0)
        uploaded_files = st.file_uploader(
            "Upload PDF files",
            type=["pdf"],
            accept_multiple_files=True,
            disabled=not model_selected,
            key=f"pdf_uploader_{uploader_key}",
            label_visibility="collapsed",
            help="Upload one or more PDF documents to enable the RAG tool.",
        )

        st.caption(
            "Processing replaces the active knowledge base with this upload batch only. A failed replacement leaves the previous index active."
        )
        # Detect submitted changes by bytes, never filenames alone.
        if uploaded_files:
            current_digest = DocumentIngestionService.upload_batch_identity(uploaded_files)
            active = st.session_state.get(K.KEY_DOCUMENT_SET)
            if active is None or active.batch_identity != current_digest:
                st.session_state[K.KEY_UNSUBMITTED_FILES] = True

        col1, col2 = st.columns([2, 1])
        submitted = col1.button(
            "Process PDFs",
            disabled=(not uploaded_files or not model_selected),
            use_container_width=True,
            type="primary",
        )
        cleared = col2.button("Clear", help="Clear PDF knowledge base", key="clear_pdfs")

        if submitted and uploaded_files:
            cls._process_pdfs(uploaded_files, embedding_provider)

        if cleared:
            cls._clear_pdfs()

        # Display loaded files
        stored_vector_store = st.session_state.get(K.KEY_VECTOR_STORE)
        stored_pdf_names = st.session_state.get(K.KEY_PDF_NAMES, [])
        if stored_vector_store and stored_pdf_names:
            with st.expander(f"{len(stored_pdf_names)} active file(s)", expanded=False):
                for name in stored_pdf_names:
                    st.text(name)

        if st.session_state.get(K.KEY_UNSUBMITTED_FILES):
            st.warning(
                "📋 New files uploaded. Click **Process PDFs** to activate them.",
                icon="⚠️",
            )

    @classmethod
    def _render_sql_section(cls) -> None:
        """Render SQL database connection panel."""
        st.caption(
            "Explore the sample music store or connect an approved SQLite file. All queries are read-only."
        )

        use_sample = st.checkbox(
            "Use Chinook sample database",
            key=K.KEY_DB_USE_SAMPLE,
            help="Uses the bundled Chinook.db (music store schema) in read-only mode.",
        )

        if use_sample:
            db_uri = "USE_SAMPLE_DB"
        else:
            db_uri = st.text_input(
                "Database URI",
                value=st.session_state.get(K.KEY_DB_URI, ""),
                placeholder="sqlite:////absolute/approved/data.db",
                type="password",
                help="Existing SQLite files only. The operator must approve directories with SQL_ALLOWED_ROOTS. No URI parameters.",
            )

        col1, col2 = st.columns(2)
        if col1.button("Connect", use_container_width=True):
            cls._connect_database(db_uri)

        if col2.button("Disconnect", use_container_width=True):
            cls._disconnect_database()

        # Show connected tables
        if st.session_state.get(K.KEY_DB_CONNECTED):
            tables = st.session_state.get(K.KEY_DB_TABLES, [])
            with st.expander(f"Schema ({len(tables)} tables)", expanded=False):
                st.text("\n".join(tables))

    @staticmethod
    def _render_utilities_section() -> None:
        """Render utility action buttons."""
        st.markdown("#### Conversation")
        col1, col2 = st.columns(2)
        has_messages = bool(st.session_state.get(K.KEY_CHAT_MESSAGES))
        col1.button(
            "Undo",
            use_container_width=True,
            disabled=not has_messages,
            help="Remove the last question and reply",
            on_click=K.undo_last_message,
        )
        col2.button(
            "Clear chat",
            use_container_width=True,
            disabled=not has_messages,
            help="Clear visible chat and model history",
            on_click=K.reset_chat,
        )
        st.button(
            "Reset workspace",
            use_container_width=True,
            help="Clear chat, remove the active PDF index, disconnect SQLite, and restore settings.",
            on_click=SidebarRenderer._reset_all,
        )

    @staticmethod
    def _render_status_metrics() -> None:
        """Keep implementation diagnostics out of the everyday workspace."""
        messages = st.session_state.get(K.KEY_CHAT_MESSAGES, [])
        st.caption(f"{len(messages) // 2} conversation turns · this session only")
        st.text(f"Model: {st.session_state.get(K.KEY_LLM_MODEL) or 'Not selected'}")
        st.caption("Chat and active source handles are not restored after a new session.")
        st.checkbox(
            "Developer mode",
            key=K.KEY_DEVELOPER_MODE,
            help="Show session ID, last tool, and safe failure codes.",
        )
        if st.session_state.get(K.KEY_DEVELOPER_MODE):
            st.text(f"Session: {st.session_state[K.KEY_SESSION_ID]}")
            st.text(f"Last tool: {st.session_state.get(K.KEY_ACTIVE_TOOL, '—')}")

    # ------------------------------------------------------------------
    # Private action handlers
    # ------------------------------------------------------------------

    @classmethod
    def _process_pdfs(cls, uploaded_files: list, embedding_provider: str) -> None:
        """
        Process uploaded PDFs: extract text, chunk, embed, and store in ChromaDB.

        Args:
            uploaded_files:    List of Streamlit uploaded file objects.
            embedding_provider: Selected embedding backend.
        """
        with st.spinner("🔄 Processing PDFs — embedding and indexing…"):
            try:
                session_id = st.session_state.get(K.KEY_SESSION_ID, "default")
                result = DocumentIngestionService.replace(
                    uploaded_files,
                    session_id,
                    embedding_provider,
                    current=st.session_state.get(K.KEY_DOCUMENT_SET),
                )
                cls._render_ingestion_report(result.report)
                if not result.ok:
                    st.error(
                        AgentResult.failure(result.error or ErrorCode.INGESTION_FAILURE).answer
                    )
                    return
                st.session_state[K.KEY_VECTOR_STORE] = result.vector_store
                st.session_state[K.KEY_DOCUMENT_SET] = result.document_set
                st.session_state[
                    K.KEY_PDF_FILES
                ] = []  # Upload bytes are not retained after indexing.
                st.session_state[K.KEY_PDF_NAMES] = result.document_set.names
                st.session_state[K.KEY_UNSUBMITTED_FILES] = False
                st.session_state[K.KEY_UPLOADER_KEY] = (
                    st.session_state.get(K.KEY_UPLOADER_KEY, 0) + 1
                )

                if result.cleanup_failed:
                    st.warning(
                        "The new knowledge base is active, but an inactive prior index could not be removed."
                    )

                st.toast(
                    f"✅ {len(result.document_set.names)} PDF(s) active — {result.report.chunks} chunks indexed.",
                    icon="📄",
                )
                logger.info(
                    "SidebarRenderer: indexed %d docs from %d PDFs into '%s'.",
                    result.report.chunks,
                    len(result.document_set.names),
                    result.document_set.collection_name,
                )

            except Exception as exc:
                st.error(
                    AgentResult.failure(
                        exc.code if isinstance(exc, ApplicationError) else ErrorCode.TOOL_FAILURE
                    ).answer
                )

    @staticmethod
    def _clear_pdfs() -> None:
        """Remove the active vector store and PDF references from session state."""
        active = st.session_state.get(K.KEY_DOCUMENT_SET)
        if not DocumentIngestionService.clear(active):
            st.error(AgentResult.failure(ErrorCode.INDEX_FAILURE).answer)
            return
        st.session_state[K.KEY_VECTOR_STORE] = None
        st.session_state[K.KEY_PDF_FILES] = []
        st.session_state[K.KEY_PDF_NAMES] = []
        st.session_state[K.KEY_DOCUMENT_SET] = None
        st.session_state[K.KEY_UNSUBMITTED_FILES] = False
        st.session_state[K.KEY_UPLOADER_KEY] = st.session_state.get(K.KEY_UPLOADER_KEY, 0) + 1
        st.toast("PDF knowledge base cleared.", icon="🗑️")

    @staticmethod
    def _reset_all() -> None:
        """Full reset deletes the active PDF collection first; failure preserves its handle."""
        if not DocumentIngestionService.clear(st.session_state.get(K.KEY_DOCUMENT_SET)):
            st.error(AgentResult.failure(ErrorCode.INDEX_FAILURE).answer)
            return
        SessionStateManager.reset_all()

    @staticmethod
    def _render_ingestion_report(report) -> None:
        if not report.outcomes:
            return
        summary = ", ".join(f"{item.name}: {item.status}" for item in report.outcomes)
        st.caption(f"Ingestion report — pages: {report.pages}, chunks: {report.chunks}. {summary}")

    @staticmethod
    def _connect_database(db_uri: str) -> None:
        """
        Validate the database URI and store connection metadata in session state.

        Args:
            db_uri: SQLAlchemy URI or ``'USE_SAMPLE_DB'`` sentinel.
        """
        if not db_uri or not db_uri.strip():
            st.error("❌ Please enter a database URI or select the sample database.")
            return

        with st.spinner("🔗 Connecting to database…"):
            try:
                tables = DatabaseConnector.get_table_names(db_uri)
            except Exception:
                st.error(
                    "⚠️ Database connection failed. "
                    "Use the sample or an approved existing SQLite file."
                )
            else:
                st.session_state[K.KEY_DB_URI] = db_uri
                st.session_state[K.KEY_DB_CONNECTED] = True
                st.session_state[K.KEY_DB_TABLES] = tables
                st.toast(f"Connection successful ({len(tables)} tables found).", icon="✅")

    @staticmethod
    def _disconnect_database() -> None:
        """Clear the database connection from session state."""
        st.session_state[K.KEY_DB_URI] = ""
        st.session_state[K.KEY_DB_CONNECTED] = False
        st.session_state[K.KEY_DB_TABLES] = []
        st.toast("Database disconnected.", icon="✖")
