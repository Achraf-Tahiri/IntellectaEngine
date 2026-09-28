"""
config/settings.py
==================
Centralized, type-safe application configuration powered by Pydantic Settings.

All configuration values are read from environment variables (or a .env file).
This module acts as the single source of truth for every tunable parameter in
the application, preventing magic strings and hard-coded values from leaking
into business logic.

Usage:
    from intellectaengine.config.settings import settings

    api_key = settings.google_api_key
    top_k   = settings.rag_top_k
"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


logger = logging.getLogger(__name__)


class AppSettings(BaseSettings):
    """
    Pydantic Settings model that reads all configuration from environment
    variables or a `.env` file located in the process working directory.

    Attributes:
        default_llm_provider: Active LLM backend (gemini | groq | openai | ollama).
        google_api_key:        Google AI Studio / Vertex API key.
        default_gemini_model:  Default Gemini model identifier.
        groq_api_key:          Groq Cloud API key.
        default_groq_model:    Default Groq model identifier.
        openai_api_key:        OpenAI API key.
        default_openai_model:  Default OpenAI model identifier.
        ollama_base_url:       Base URL for the local Ollama server.
        default_ollama_model:  Default Ollama model identifier.
        default_embedding_provider: Embedding backend provider.
        huggingface_embedding_model: HuggingFace sentence-transformer model name.
        chroma_persist_base_dir: Filesystem path for persisting ChromaDB collections.
        rag_top_k:             Number of chunks to retrieve per RAG query.
        rag_chunk_size:        Character size of each document chunk.
        rag_chunk_overlap:     Character overlap between adjacent chunks.
        web_search_max_results: Maximum DuckDuckGo results per search.
        web_scrape_timeout:    HTTP request timeout in seconds for web scraping.
        sql_top_k:             Maximum SQL rows returned by the SQL agent.
        app_title:             Display title shown in the Streamlit UI.
        app_subtitle:          Subtitle / tagline shown in the Streamlit UI.
        log_level:             Python logging level (DEBUG | INFO | WARNING | ERROR).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        hide_input_in_errors=True,
    )

    # -------------------------------------------------------------------------
    # LLM Provider
    # -------------------------------------------------------------------------
    default_llm_provider: Literal["gemini", "groq", "openai", "ollama"] = Field(
        default="gemini",
        description="Active LLM provider.",
    )

    # -------------------------------------------------------------------------
    # Google Gemini
    # -------------------------------------------------------------------------
    google_api_key: str = Field(default="", repr=False, description="Google AI API key.")
    default_gemini_model: str = Field(
        default="gemini-3.5-flash",
        description="Default Gemini model identifier.",
    )

    # -------------------------------------------------------------------------
    # Groq
    # -------------------------------------------------------------------------
    groq_api_key: str = Field(default="", repr=False, description="Groq Cloud API key.")
    default_groq_model: str = Field(
        default="llama-3.1-8b-instant",
        description="Default Groq model identifier.",
    )

    # -------------------------------------------------------------------------
    # OpenAI
    # -------------------------------------------------------------------------
    openai_api_key: str = Field(default="", repr=False, description="OpenAI API key.")
    default_openai_model: str = Field(
        default="gpt-4o-mini",
        description="Default OpenAI model identifier.",
    )

    # -------------------------------------------------------------------------
    # Ollama (local)
    # -------------------------------------------------------------------------
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        description="Base URL for the local Ollama server.",
    )
    default_ollama_model: str = Field(
        default="llama3.2",
        description="Default Ollama model identifier.",
    )

    # -------------------------------------------------------------------------
    # Embeddings
    # -------------------------------------------------------------------------
    default_embedding_provider: Literal["gemini", "huggingface", "openai", "fastembed"] = Field(
        default="huggingface",
        description="Embedding backend provider.",
    )
    huggingface_embedding_model: str = Field(
        default="sentence-transformers/all-MiniLM-L12-v2",
        description="HuggingFace sentence-transformer model name.",
    )

    # -------------------------------------------------------------------------
    # ChromaDB
    # -------------------------------------------------------------------------
    chroma_persist_base_dir: str = Field(
        default="./data/chroma",
        description="Filesystem path for persisting ChromaDB collections.",
    )

    # -------------------------------------------------------------------------
    # RAG Retrieval
    # -------------------------------------------------------------------------
    rag_top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of document chunks to retrieve per query.",
    )
    rag_chunk_size: int = Field(
        default=1000,
        ge=100,
        description="Character size of each document chunk.",
    )
    rag_chunk_overlap: int = Field(
        default=200,
        ge=0,
        description="Character overlap between adjacent chunks.",
    )
    rag_max_upload_bytes: int = Field(
        default=20_000_000, ge=1, description="Maximum bytes accepted per PDF upload."
    )
    rag_max_files: int = Field(default=10, ge=1, le=100, description="Maximum PDFs per batch.")
    rag_max_pages: int = Field(
        default=500, ge=1, description="Maximum attempted page extractions per batch."
    )
    rag_max_chunks: int = Field(
        default=5_000,
        ge=1,
        description="Maximum produced chunks per batch, including discarded chunks.",
    )
    rag_context_char_limit: int = Field(
        default=12_000,
        ge=100,
        description="Maximum context characters including source labels and separators.",
    )

    # -------------------------------------------------------------------------
    # Web Research
    # -------------------------------------------------------------------------
    web_search_max_results: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum DuckDuckGo results per search.",
    )
    web_scrape_timeout: int = Field(
        default=15,
        ge=1,
        le=60,
        description="Jina connect/read ceiling and DDGS request timeout in seconds.",
    )

    web_query_char_limit: int = Field(default=1000, ge=1, le=10_000)
    web_url_char_limit: int = Field(default=2048, ge=128, le=8192)
    web_observation_char_limit: int = Field(default=6000, ge=128, le=100_000)
    web_response_byte_limit: int = Field(default=262_144, ge=1, le=2_000_000)
    web_elapsed_seconds: float = Field(default=30, gt=0, le=120, allow_inf_nan=False)

    # -------------------------------------------------------------------------
    # SQL Agent
    # -------------------------------------------------------------------------
    sql_top_k: int = Field(
        default=10,
        ge=1,
        le=1000,
        description="Maximum SQL rows returned by the SQL agent.",
    )
    sql_allowed_roots: list[str] = Field(default_factory=list, repr=False)
    sql_cell_char_limit: int = Field(default=1000, ge=32, le=100_000)
    sql_observation_char_limit: int = Field(default=12_000, ge=128, le=100_000)
    sql_statement_seconds: float = Field(default=2.0, gt=0, le=30, allow_inf_nan=False)
    sql_statement_steps: int = Field(default=1_000_000, ge=1000, le=100_000_000)
    sql_lock_timeout_ms: int = Field(default=250, ge=1, le=5000)

    @field_validator("sql_allowed_roots")
    @classmethod
    def absolute_sql_roots(cls, values: list[str]) -> list[str]:
        from pathlib import Path

        if any(not value.strip() or not Path(value).is_absolute() for value in values):
            raise ValueError("SQL allowed roots must be absolute directory paths.")
        return values

    # -------------------------------------------------------------------------
    # Application
    # -------------------------------------------------------------------------
    app_title: str = Field(
        default="IntellectaEngine",
        description="Display title shown in the Streamlit UI.",
    )
    app_subtitle: str = Field(
        default="Unified AI Knowledge & Research Platform",
        description="Subtitle shown in the Streamlit UI.",
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO",
        description="Python logging level.",
    )

    # -------------------------------------------------------------------------
    # Derived helpers
    # -------------------------------------------------------------------------
    @field_validator(
        "default_gemini_model",
        "default_groq_model",
        "default_openai_model",
        "default_ollama_model",
        "huggingface_embedding_model",
    )
    @classmethod
    def nonempty_model(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Model identifier must not be blank.")
        return value.strip()

    @field_validator("rag_chunk_overlap")
    @classmethod
    def overlap_less_than_chunk(cls, v: int, info) -> int:
        """Ensures chunk overlap is strictly less than chunk_size.

        Args:
            v: The overlap value being validated.
            info: Pydantic validation info object containing other field values.

        Returns:
            The validated overlap value.

        Raises:
            ValueError: If overlap is greater than or equal to chunk_size.
        """
        chunk_size = info.data.get("rag_chunk_size", 1000)
        if v >= chunk_size:
            raise ValueError(
                f"rag_chunk_overlap ({v}) must be less than rag_chunk_size ({chunk_size})."
            )
        return v

    def get_default_model(self, provider: str) -> str:
        """Returns the default model identifier for a given provider.

        Args:
            provider: LLM provider name. One of 'gemini', 'groq', 'openai', 'ollama'.

        Returns:
            The default model string for the requested provider.

        Raises:
            ValueError: If the provider is not recognised.
        """
        mapping: dict[str, str] = {
            "gemini": self.default_gemini_model,
            "groq": self.default_groq_model,
            "openai": self.default_openai_model,
            "ollama": self.default_ollama_model,
        }
        if provider not in mapping:
            raise ValueError(f"Unknown provider. Choose from: {list(mapping.keys())}.")
        return mapping[provider]

    def get_available_models(self, provider: str) -> list[str]:
        """Returns the list of selectable model names for a given provider.

        Args:
            provider: LLM provider name.

        Returns:
            List of model name strings for the given provider.
        """
        catalogue: dict[str, list[str]] = {
            "gemini": [
                "gemini-3.5-flash",
                "gemini-2.5-flash",
                "gemini-2.5-pro",
                "gemini-2.0-flash",
                "gemini-1.5-pro",
            ],
            "groq": [
                "llama-3.1-8b-instant",
                "llama3-70b-8192",
                "mixtral-8x7b-32768",
                "gemma2-9b-it",
            ],
            "openai": [
                "gpt-4o-mini",
                "gpt-4o",
                "gpt-4-turbo",
                "o1-mini",
            ],
            "ollama": [
                "llama3.2",
                "llama3.1",
                "mistral",
                "phi3",
                "codellama",
            ],
        }
        return catalogue.get(provider, [])


# Singleton instance — import this throughout the application.
settings = AppSettings()

# Configure root logger once at import time.
logging.basicConfig(
    level=getattr(logging, settings.log_level, logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
