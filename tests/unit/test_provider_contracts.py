"""Factory configuration and initialization checks without creating providers."""

import pytest


@pytest.mark.parametrize("kind", ["llm", "embedding"])
@pytest.mark.parametrize("provider", ["unsupported", "", "gemini", "openai"])
def test_invalid_provider_or_missing_credentials(kind, provider):
    from intellectaengine.config.settings import AppSettings
    from intellectaengine.core.contracts import ApplicationError, ErrorCode
    from intellectaengine.core.embedding_factory import EmbeddingFactory
    from intellectaengine.core.llm_factory import LLMFactory

    factory = LLMFactory if kind == "llm" else EmbeddingFactory
    with pytest.raises(ApplicationError) as failure:
        factory.create(provider, config=AppSettings(_env_file=None))
    assert failure.value.code == ErrorCode.INVALID_CONFIGURATION


@pytest.mark.parametrize("provider", ["gemini", "groq", "openai", "ollama"])
def test_llm_uses_injected_settings_and_never_switches_provider(monkeypatch, provider):
    from intellectaengine.config.settings import AppSettings
    from intellectaengine.core.llm_factory import LLMFactory

    config = AppSettings(
        _env_file=None,
        google_api_key="synthetic",
        groq_api_key="synthetic",
        openai_api_key="synthetic",
        **{f"default_{provider}_model": "custom-model"},
    )
    seen = []
    sentinel = object()
    monkeypatch.setattr(LLMFactory, "_build", lambda *args: seen.append(args) or sentinel)
    assert LLMFactory.create(provider, config=config) is sentinel
    assert seen == [(provider, "custom-model", 0.3, False, config)]


@pytest.mark.parametrize("kind", ["llm", "embedding"])
def test_initialization_error_payload_is_discarded(monkeypatch, caplog, kind):
    from intellectaengine.config.settings import AppSettings
    from intellectaengine.core.contracts import ApplicationError, ErrorCode
    from intellectaengine.core.embedding_factory import EmbeddingFactory
    from intellectaengine.core.llm_factory import LLMFactory

    factory = LLMFactory if kind == "llm" else EmbeddingFactory

    def fail(*args):
        raise ValueError("SYNTHETIC-SECRET https://user:password@host private request")

    monkeypatch.setattr(factory, "_build", fail)
    with pytest.raises(ApplicationError) as failure:
        factory.create(
            "openai", config=AppSettings(_env_file=None, openai_api_key="SYNTHETIC-SECRET")
        )
    assert failure.value.code == ErrorCode.PROVIDER_FAILURE
    assert "SYNTHETIC-SECRET" not in str(failure.value) + caplog.text
    assert "password" not in str(failure.value) + caplog.text


def test_embedding_custom_default_is_injected(monkeypatch):
    from intellectaengine.config.settings import AppSettings
    from intellectaengine.core.embedding_factory import EmbeddingFactory

    config = AppSettings(_env_file=None, default_embedding_provider="fastembed")
    monkeypatch.setattr(EmbeddingFactory, "_build", lambda *args: args)
    assert EmbeddingFactory.create(config=config) == ("fastembed", None, config)
