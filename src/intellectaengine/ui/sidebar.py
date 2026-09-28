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

        Sections rendered (top to bottom):
            1. Branding / logo lockup
            2. LLM Provider & Model selection
            3. Embedding Provider selection
            4. Agent Mode selector
            5. PDF Upload panel
            6. SQL Database connection panel
            7. Utility actions (reset / clear / undo)
            8. System status metrics

        Example:
            >>> with st.sidebar:
            ...     SidebarRenderer.render()
        """
        cls._render_branding()
        st.markdown("---")
        cls._render_llm_section()
        st.markdown("---")
        cls._render_agent_mode_section()
        st.markdown("---")
        cls._render_pdf_section()
        st.markdown("---")
        cls._render_sql_section()
        st.markdown("---")
        cls._render_utilities_section()
        st.markdown("---")
        cls._render_status_metrics()

    # ------------------------------------------------------------------
    # Section renderers
    # ------------------------------------------------------------------

    @staticmethod
    def _render_branding() -> None:
        """Render the sidebar logo and tagline with premium styling."""
        st.markdown(
            """
        <div style="
            text-align: center;
            padding: 1rem 0.5rem 1.25rem;
            background: linear-gradient(160deg, rgba(139,92,246,0.08), rgba(59,130,246,0.05));
            border: 1px solid rgba(139,92,246,0.15);
            border-radius: 16px;
            margin-bottom: 0.5rem;
            position: relative;
            overflow: hidden;
        ">
            <div style="
                position: absolute; inset: 0;
                background: radial-gradient(circle at 50% 0%, rgba(139,92,246,0.08), transparent 70%);
                pointer-events: none;
            "></div>
            <div style="
                width: 48px; height: 48px;
                margin: 0 auto 0.5rem;
                background: linear-gradient(135deg, rgba(139,92,246,0.18), rgba(59,130,246,0.12));
                border: 1px solid rgba(139,92,246,0.25);
                border-radius: 14px;
                display: flex; align-items: center; justify-content: center;
                font-size: 1.6rem;
                box-shadow: 0 0 20px rgba(139,92,246,0.10);
            ">🧠</div>
            <h3 style="
                margin: 0;
                font-size: 1.05rem;
                font-weight: 800;
                background: linear-gradient(135deg, #E2E8F0, #A78BFA, #93C5FD);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
                letter-spacing: -0.02em;
            ">IntellectaEngine</h3>
            <p style="
                color: #8492A6;
                font-size: 0.65rem;
                margin: 4px 0 0;
                font-weight: 500;
                letter-spacing: 0.06em;
                text-transform: uppercase;
            ">Knowledge · Intelligence · Insight</p>
        </div>
        """,
            unsafe_allow_html=True,
        )

    @staticmethod
    def _render_llm_section() -> None:
        """Render LLM provider, model, and embedding provider selectors."""
        st.markdown("#### ⚙️ Model Configuration")

        # --- Provider ---
        provider = st.selectbox(
            "🔌 LLM Provider",
            options=LLMFactory.list_providers(),
            key=K.KEY_LLM_PROVIDER,
            on_change=K.provider_changed,
            help="Select the AI provider powering all reasoning.",
        )

        # --- Model ---
        st.text_input(
            "🧠 Model",
            key=K.KEY_LLM_MODEL,
            help="Use the configured default or enter a model identifier available from this provider.",
        )

        # API key validation hint
        if provider == "gemini" and not settings.google_api_key:
            st.warning("⚠️ GOOGLE_API_KEY not set in .env", icon="🔑")
        elif provider == "groq" and not settings.groq_api_key:
            st.warning("⚠️ GROQ_API_KEY not set in .env", icon="🔑")
        elif provider == "openai" and not settings.openai_api_key:
            st.warning("⚠️ OPENAI_API_KEY not set in .env", icon="🔑")
        elif provider == "ollama":
            st.info(
                "🖥️ Ollama uses the configured local server.",
                icon="ℹ️",
            )

        st.markdown("&nbsp;")

        # --- Embedding provider ---
        st.selectbox(
            "📐 Embedding Provider",
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
        st.markdown("#### 🤖 Agent Routing Mode")

        mode_options = {
            "auto": "🔄 Auto (Router decides)",
            "rag": "📄 Force: RAG Documents",
            "sql": "🗄️ Force: SQL Database",
            "web": "🌐 Force: Web Research",
            "chat": "💬 Force: Direct Chat",
        }

        current_mode = st.session_state.get(K.KEY_AGENT_MODE, "auto")
        selected_label = st.radio(
            "Routing Strategy",
            options=list(mode_options.values()),
            index=list(mode_options.keys()).index(current_mode),
            label_visibility="collapsed",
            help=(
                "Auto mode lets the router agent decide which tool to use "
                "based on your query. Force modes bypass the router."
            ),
        )

        # Map label back to key
        for key, label in mode_options.items():
            if label == selected_label:
                st.session_state[K.KEY_AGENT_MODE] = key
                break

    @classmethod
    def _render_pdf_section(cls) -> None:
        """Render PDF file uploader and processing controls."""
        st.markdown("#### 📄 PDF Knowledge Base")

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

        col1, col2 = st.columns([3, 1])
        submitted = col1.button(
            "⚡ Process PDFs",
            disabled=(not uploaded_files or not model_selected),
            use_container_width=True,
            type="primary",
        )
        cleared = col2.button("🗑️", help="Clear PDF knowledge base")

        if submitted and uploaded_files:
            cls._process_pdfs(uploaded_files, embedding_provider)

        if cleared:
            cls._clear_pdfs()

        # Display loaded files
        stored_vector_store = st.session_state.get(K.KEY_VECTOR_STORE)
        stored_pdf_names = st.session_state.get(K.KEY_PDF_NAMES, [])
        if stored_vector_store and stored_pdf_names:
            with st.expander(f"📎 {len(stored_pdf_names)} file(s) loaded", expanded=False):
                for name in stored_pdf_names:
                    st.markdown(f"- `{name}`")

        if st.session_state.get(K.KEY_UNSUBMITTED_FILES):
            st.warning(
                "📋 New files uploaded. Click **⚡ Process PDFs** to activate them.",
                icon="⚠️",
            )

    @classmethod
    def _render_sql_section(cls) -> None:
        """Render SQL database connection panel."""
        st.markdown("#### 🗄️ SQL Database")
        st.caption(
            "SQLite only, read-only. Custom files require operator-configured "
            "SQL_ALLOWED_ROOTS. Remote databases are not supported."
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
                help="Existing SQLite files in approved directories only. No URI parameters.",
            )

        col1, col2 = st.columns(2)
        if col1.button("🔗 Connect", use_container_width=True):
            cls._connect_database(db_uri)

        if col2.button("✖ Disconnect", use_container_width=True):
            cls._disconnect_database()

        # Show connected tables
        if st.session_state.get(K.KEY_DB_CONNECTED):
            tables = st.session_state.get(K.KEY_DB_TABLES, [])
            with st.expander(f"📊 Schema ({len(tables)} tables)", expanded=False):
                for table in tables:
                    st.markdown(f"- `{table}`")

    @staticmethod
    def _render_utilities_section() -> None:
        """Render utility action buttons."""
        st.markdown("#### 🛠️ Utilities")

        col1, col2, col3 = st.columns(3)

        # Callbacks run before widget creation, so Reset can replace widget state.
        col1.button(
            "🔄 Reset",
            use_container_width=True,
            help="Full application reset",
            on_click=SidebarRenderer._reset_all,
        )
        col2.button(
            "🧹 Clear",
            use_container_width=True,
            help="Clear visible chat and model history",
            on_click=SessionStateManager.reset_chat,
        )
        col3.button(
            "↩️ Undo",
            use_container_width=True,
            help="Remove the last question and reply",
            on_click=SessionStateManager.undo_last_message,
        )

        # Developer mode toggle
        st.checkbox(
            "🔬 Developer Mode",
            key=K.KEY_DEVELOPER_MODE,
            help="Show debug info: session ID, active tool, and safe failure codes.",
        )

    @staticmethod
    def _render_status_metrics() -> None:
        """Render live status metrics at the bottom of the sidebar."""
        provider = st.session_state.get(K.KEY_LLM_PROVIDER, "—")
        model = st.session_state.get(K.KEY_LLM_MODEL, "—") or "—"
        has_docs = st.session_state.get(K.KEY_VECTOR_STORE) is not None
        has_db = st.session_state.get(K.KEY_DB_CONNECTED, False)
        last_tool = st.session_state.get(K.KEY_ACTIVE_TOOL, "—")
        msg_count = len(st.session_state.get(K.KEY_CHAT_MESSAGES, []))

        st.markdown("#### 📊 System Status")
        col1, col2 = st.columns(2)
        col1.metric("🔌 Provider", provider.capitalize())
        col2.metric("💬 Messages", msg_count)

        col3, col4 = st.columns(2)
        col3.metric("📄 Docs", "✅" if has_docs else "❌")
        col4.metric("🗄️ DB", "✅" if has_db else "❌")

        st.caption(f"🏷️ Model: `{model[:25]}`")
        st.caption(f"🔧 Last tool: `{last_tool}`")

        if st.session_state.get(K.KEY_DEVELOPER_MODE):
            session_id = st.session_state.get(K.KEY_SESSION_ID, "?")
            st.caption(f"🆔 Session: `{session_id}`")

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
