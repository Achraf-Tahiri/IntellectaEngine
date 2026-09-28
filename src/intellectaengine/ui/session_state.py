"""
ui/session_state.py
====================
Centralised Streamlit Session State Manager.

This module is the single source of truth for all ``st.session_state`` keys
used across the IntellectaEngine application. By centralising initialisation
here, we eliminate ``KeyError`` exceptions from accessing uninitialised state,
prevent accidental key collisions across UI modules, and provide a typed
reference for every piece of transient application state.

Design principles:
- All keys are defined as class constants (no magic strings scattered in UI code)
- Default values are always safe (None, [], {}, False)
- The ``initialise()`` method is idempotent — safe to call multiple times

Usage:
    from intellectaengine.ui.session_state import SessionStateManager

    # Call once at app startup
    SessionStateManager.initialise()

    # Access state throughout the app
    st.session_state[SessionStateManager.KEY_VECTOR_STORE]
"""

from __future__ import annotations

import logging
import uuid
from copy import deepcopy
from typing import Any

import streamlit as st

from intellectaengine.core.memory_store import MemoryStore
from intellectaengine.config.settings import AppSettings, settings

logger = logging.getLogger(__name__)


class SessionStateManager:
    """
    Idempotent initialiser and typed accessor for ``st.session_state``.

    All Streamlit session state keys are defined as class-level string
    constants, preventing hard-coded strings from spreading across modules.

    Usage:
        >>> SessionStateManager.initialise()
        >>> st.session_state[SessionStateManager.KEY_LLM_PROVIDER]
        'gemini'
    """

    # ------------------------------------------------------------------
    # Key constants — use these everywhere instead of raw strings
    # ------------------------------------------------------------------

    # LLM configuration
    KEY_LLM_PROVIDER: str = "llm_provider"
    KEY_LLM_MODEL: str = "llm_model"
    KEY_EMBEDDING_PROVIDER: str = "embedding_provider"

    # RAG / PDF state
    KEY_VECTOR_STORE: str = "vector_store"
    KEY_PDF_FILES: str = "pdf_files"
    KEY_UNSUBMITTED_FILES: str = "unsubmitted_files"
    KEY_UPLOADER_KEY: str = "uploader_key"
    KEY_PDF_NAMES: str = "pdf_names"
    KEY_DOCUMENT_SET: str = "document_set"

    # SQL state
    KEY_DB_URI: str = "db_uri"
    KEY_DB_CONNECTED: str = "db_connected"
    KEY_DB_TABLES: str = "db_tables"
    KEY_DB_USE_SAMPLE: str = "sql_use_sample"

    # Chat state
    KEY_CHAT_MESSAGES: str = "chat_messages"
    KEY_SESSION_ID: str = "session_id"
    KEY_MEMORY: str = "conversation_memory"

    # Agentic state
    KEY_ACTIVE_TOOL: str = "last_tool_used"
    KEY_AGENT_MODE: str = "agent_mode"  # 'auto' | 'rag' | 'sql' | 'web' | 'chat'

    # UI state
    KEY_SHOW_SOURCES: str = "show_sources"
    KEY_DEVELOPER_MODE: str = "developer_mode"

    # Defaults for every key
    _DEFAULTS: dict[str, Any] = {
        KEY_LLM_PROVIDER: None,
        KEY_LLM_MODEL: None,
        KEY_EMBEDDING_PROVIDER: None,
        KEY_VECTOR_STORE: None,
        KEY_PDF_FILES: [],
        KEY_UNSUBMITTED_FILES: False,
        KEY_UPLOADER_KEY: 0,
        KEY_PDF_NAMES: [],
        KEY_DOCUMENT_SET: None,
        KEY_DB_URI: "",
        KEY_DB_CONNECTED: False,
        KEY_DB_TABLES: [],
        KEY_DB_USE_SAMPLE: False,
        KEY_CHAT_MESSAGES: [],
        KEY_MEMORY: None,  # One instance per Streamlit session
        KEY_SESSION_ID: None,  # Generated on first initialise()
        KEY_ACTIVE_TOOL: "—",
        KEY_AGENT_MODE: "auto",
        KEY_SHOW_SOURCES: True,
        KEY_DEVELOPER_MODE: False,
    }

    @classmethod
    def initialise(cls, config: AppSettings | None = None) -> None:
        """
        Initialise all session state keys to their default values if not
        already present.

        This method is idempotent — calling it multiple times is safe and
        will not overwrite existing values. It should be called once at the
        top of ``app.py`` before any other UI code runs.

        Side effects:
            Generates a unique ``session_id`` UUID on first call.

        Example:
            >>> SessionStateManager.initialise()
            >>> st.session_state["session_id"]  # e.g. 'a3f2c1d0-...'
        """
        config = config or settings
        defaults = {
            **cls._DEFAULTS,
            cls.KEY_LLM_PROVIDER: config.default_llm_provider,
            cls.KEY_LLM_MODEL: config.get_default_model(
                st.session_state.get(cls.KEY_LLM_PROVIDER, config.default_llm_provider)
            ),
            cls.KEY_EMBEDDING_PROVIDER: config.default_embedding_provider,
        }
        for key, default_value in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = deepcopy(default_value)

        if st.session_state[cls.KEY_MEMORY] is None:
            st.session_state[cls.KEY_MEMORY] = MemoryStore()

        # Generate a unique session ID for memory isolation
        if st.session_state[cls.KEY_SESSION_ID] is None:
            st.session_state[cls.KEY_SESSION_ID] = str(uuid.uuid4())
            logger.info(
                "SessionState: new session initialised with ID='%s'.",
                st.session_state[cls.KEY_SESSION_ID],
            )

    @classmethod
    def provider_changed(cls) -> None:
        """Widget callback runs before model widget recreation."""
        st.session_state[cls.KEY_LLM_MODEL] = settings.get_default_model(
            st.session_state[cls.KEY_LLM_PROVIDER]
        )

    @classmethod
    def reset_all(cls, config: AppSettings | None = None) -> None:
        """
        Clear and re-initialise all session state keys to their defaults.

        This is the "full reset" action triggered by the sidebar Reset button.
        It clears the vector store, chat history, DB connection, and all
        uploaded file references.

        Example:
            >>> SessionStateManager.reset_all()
        """
        cls.reset_chat()
        for key in cls._DEFAULTS:
            if key in st.session_state:
                del st.session_state[key]
        cls.initialise(config)
        logger.info("SessionState: full reset performed.")

    @classmethod
    def reset_chat(cls) -> None:
        """
        Clear only the chat message history and the last-used-tool indicator.

        Example:
            >>> SessionStateManager.reset_chat()
        """
        memory = st.session_state.get(cls.KEY_MEMORY)
        if memory is not None:
            memory.clear()
        st.session_state[cls.KEY_CHAT_MESSAGES] = []
        st.session_state[cls.KEY_ACTIVE_TOOL] = "—"
        logger.info("SessionState: chat history cleared.")

    @classmethod
    def undo_last_message(cls) -> bool:
        """
        Remove the last user + assistant message pair from chat history.

        Returns:
            ``True`` if a message was removed, ``False`` if history was
            already empty.

        Example:
            >>> removed = SessionStateManager.undo_last_message()
        """
        messages = st.session_state.get(cls.KEY_CHAT_MESSAGES, [])
        if not messages:
            return False
        cls._replace_conversation(messages[:-2])
        return True

    @classmethod
    def get(cls, key: str, default: Any = None) -> Any:
        """
        Safely retrieve a session state value with a fallback default.

        Args:
            key:     The session state key to retrieve.
            default: Value returned if the key is not found.

        Returns:
            The stored value or the provided default.

        Example:
            >>> SessionStateManager.get(SessionStateManager.KEY_LLM_PROVIDER)
            'gemini'
        """
        return st.session_state.get(key, default)

    @classmethod
    def set(cls, key: str, value: Any) -> None:
        """
        Set a session state value.

        Args:
            key:   The session state key to set.
            value: The value to store.

        Example:
            >>> SessionStateManager.set(SessionStateManager.KEY_LLM_PROVIDER, "groq")
        """
        st.session_state[key] = value

    @classmethod
    def complete_turn(cls, query: str, answer: str, tool: str = "—", sources=()) -> None:
        """Commit one final reply (including errors) to visible and model history.

        Called once by the UI after dispatch. Tools and executors do not write
        memory. An interrupted request with no final reply is not committed.
        """
        messages = [
            *st.session_state[cls.KEY_CHAT_MESSAGES],
            {"role": "user", "content": query, "tool": "—"},
            {"role": "assistant", "content": answer, "tool": tool, "sources": list(sources)},
        ]
        cls._replace_conversation(messages)

    @classmethod
    def _replace_conversation(cls, messages: list[dict]) -> None:
        st.session_state[cls.KEY_MEMORY].replace_from_transcript(messages)
        st.session_state[cls.KEY_CHAT_MESSAGES] = messages
        st.session_state[cls.KEY_ACTIVE_TOOL] = messages[-1]["tool"] if messages else "—"
