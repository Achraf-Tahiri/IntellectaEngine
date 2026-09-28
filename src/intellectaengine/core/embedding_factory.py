"""
core/embedding_factory.py
==========================
Multi-Provider Embedding Factory using the Factory Method design pattern.

This module mirrors the structure of ``LLMFactory`` but is responsible for
producing embedding models used by the ChromaDB vector store connector.
Supports HuggingFace sentence-transformers, Google Gemini embeddings,
OpenAI embeddings, and FastEmbed for local CPU embeddings.

Usage:
    from intellectaengine.core.embedding_factory import EmbeddingFactory

    embedder = EmbeddingFactory.create(provider="huggingface")
    vectors = embedder.embed_query("What is retrieval augmented generation?")
"""

from __future__ import annotations

import logging
from typing import Optional

from langchain_core.embeddings import Embeddings

from intellectaengine.config.settings import AppSettings, settings
from intellectaengine.core.contracts import ApplicationError, ErrorCode

logger = logging.getLogger(__name__)


class EmbeddingFactory:
    """
    Stateless factory that instantiates and returns a LangChain-compatible
    ``Embeddings`` model for any supported embedding provider.

    The factory reads configuration from the application settings singleton.
    Callers never need to handle API keys or model paths directly.

    Example:
        >>> embedder = EmbeddingFactory.create("huggingface")
        >>> vec = embedder.embed_query("hello world")
        >>> len(vec)  # 384
        384
    """

    # Human-readable labels used in the UI selector.
    PROVIDER_LABELS: dict[str, str] = {
        "huggingface": "HuggingFace (local)",
        "fastembed": "FastEmbed (local, lightweight)",
        "gemini": "Google Gemini Embeddings",
        "openai": "OpenAI Embeddings",
    }

    @classmethod
    def resolve_model(
        cls, provider: str, model: Optional[str] = None, config: AppSettings | None = None
    ) -> str:
        """Return the explicit embedding model identifier used in index identity."""
        config = config or settings
        resolved_provider = provider.lower().strip()
        defaults = {
            "huggingface": config.huggingface_embedding_model,
            "fastembed": "BAAI/bge-small-en-v1.5",
            "gemini": "models/embedding-001",
            "openai": "text-embedding-3-small",
        }
        if resolved_provider not in defaults or (model is not None and not model.strip()):
            raise ApplicationError(ErrorCode.INVALID_CONFIGURATION)
        return (model or defaults[resolved_provider]).strip()

    @classmethod
    def create(
        cls,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        config: AppSettings | None = None,
    ) -> Embeddings:
        """
        Instantiate and return an embedding model for the specified provider.

        Args:
            provider: The embedding backend. If ``None``, falls back to
                      ``settings.default_embedding_provider``.
            model:    Optional explicit model name / path. Overrides the
                      provider-specific default when supplied.
            config:   Validated settings override; defaults to application settings.

        Returns:
            A LangChain ``Embeddings`` instance ready for use with ChromaDB.

        Raises:
            ApplicationError: Invalid configuration or provider initialization failure.

        Example:
            >>> emb = EmbeddingFactory.create(provider="gemini")
            >>> emb.embed_query("test")
        """
        config = config or settings
        resolved_provider = (
            (config.default_embedding_provider if provider is None else provider).lower().strip()
        )
        if resolved_provider not in cls.PROVIDER_LABELS or (
            model is not None and not model.strip()
        ):
            raise ApplicationError(ErrorCode.INVALID_CONFIGURATION)
        key = {"gemini": config.google_api_key, "openai": config.openai_api_key}.get(
            resolved_provider
        )
        if key is not None and not key.strip():
            raise ApplicationError(ErrorCode.INVALID_CONFIGURATION)
        try:
            return cls._build(resolved_provider, model, config)
        except ApplicationError:
            raise
        except Exception:
            raise ApplicationError(ErrorCode.PROVIDER_FAILURE) from None

    @classmethod
    def _build(cls, provider: str, model: Optional[str], config: AppSettings) -> Embeddings:
        """
        Internal dispatch that constructs the concrete embedder instance.

        Args:
            provider: Normalised provider string.
            model:    Optional model override.

        Returns:
            Concrete ``Embeddings`` subclass instance.

        Raises:
            ValueError: If the provider is not recognised.
        """
        if provider == "huggingface":
            return cls._build_huggingface(model, config)
        elif provider == "fastembed":
            return cls._build_fastembed(model, config)
        elif provider == "gemini":
            return cls._build_gemini(model, config)
        elif provider == "openai":
            return cls._build_openai(model, config)
        else:
            raise ValueError(
                f"Unknown embedding provider: '{provider}'. "
                f"Supported: {list(cls.PROVIDER_LABELS.keys())}"
            )

    # ------------------------------------------------------------------
    # Provider-specific builders
    # ------------------------------------------------------------------

    @staticmethod
    def _build_huggingface(model: Optional[str], config: AppSettings) -> Embeddings:
        """
        Build a HuggingFace sentence-transformers embedding model (runs locally).

        Args:
            model: Sentence-transformer model name. Falls back to
                   ``config.huggingface_embedding_model`` when ``None``.

        Returns:
            ``HuggingFaceEmbeddings`` instance.
        """
        from langchain_community.embeddings import HuggingFaceEmbeddings

        resolved_model = model or config.huggingface_embedding_model
        return HuggingFaceEmbeddings(model_name=resolved_model)

    @staticmethod
    def _build_fastembed(model: Optional[str], config: AppSettings) -> Embeddings:
        """
        Build a FastEmbed embedding model (lightweight, no GPU required).

        Args:
            model: FastEmbed model name. Defaults to 'BAAI/bge-small-en-v1.5'.

        Returns:
            ``FastEmbedEmbeddings`` instance.
        """
        from langchain_community.embeddings.fastembed import FastEmbedEmbeddings

        resolved_model = model or "BAAI/bge-small-en-v1.5"
        return FastEmbedEmbeddings(model_name=resolved_model)

    @staticmethod
    def _build_gemini(model: Optional[str], config: AppSettings) -> Embeddings:
        """
        Build a Google Gemini embedding model.

        Args:
            model: Gemini embedding model ID. Defaults to 'models/embedding-001'.

        Returns:
            ``GoogleGenerativeAIEmbeddings`` instance.

        Raises:
            RuntimeError: If GOOGLE_API_KEY is not set.
        """
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        api_key = config.google_api_key
        if not api_key:
            raise RuntimeError("GOOGLE_API_KEY is not set. Required for Gemini embeddings.")
        resolved_model = model or "models/embedding-001"
        return GoogleGenerativeAIEmbeddings(
            model=resolved_model,
            google_api_key=api_key,
        )

    @staticmethod
    def _build_openai(model: Optional[str], config: AppSettings) -> Embeddings:
        """
        Build an OpenAI embedding model.

        Args:
            model: OpenAI embedding model ID. Defaults to 'text-embedding-3-small'.

        Returns:
            ``OpenAIEmbeddings`` instance.

        Raises:
            RuntimeError: If OPENAI_API_KEY is not set.
        """
        from langchain_openai import OpenAIEmbeddings

        api_key = config.openai_api_key
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set. Required for OpenAI embeddings.")
        resolved_model = model or "text-embedding-3-small"
        return OpenAIEmbeddings(model=resolved_model, api_key=api_key)

    @classmethod
    def list_providers(cls) -> list[str]:
        """
        Return the list of all supported embedding provider identifiers.

        Returns:
            Sorted list of provider key strings.
        """
        return sorted(cls.PROVIDER_LABELS.keys())
