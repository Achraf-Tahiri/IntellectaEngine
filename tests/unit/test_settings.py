import pytest
from pydantic import ValidationError


def test_defaults_need_no_credentials():
    from intellectaengine.config.settings import AppSettings

    settings = AppSettings(_env_file=None)
    assert settings.default_embedding_provider == "huggingface"
    assert settings.google_api_key == settings.groq_api_key == settings.openai_api_key == ""
    assert 0 <= settings.rag_chunk_overlap < settings.rag_chunk_size


def test_environment_overrides_defaults(monkeypatch):
    from intellectaengine.config.settings import AppSettings

    monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "ollama")
    monkeypatch.setenv("DEFAULT_OLLAMA_MODEL", "test-model")
    monkeypatch.setenv("RAG_TOP_K", "3")
    settings = AppSettings(_env_file=None)
    assert settings.default_llm_provider == "ollama"
    assert settings.get_default_model("ollama") == "test-model"
    assert settings.rag_top_k == 3


@pytest.mark.parametrize(
    "values",
    [
        {"default_llm_provider": "unsupported"},
        {"default_embedding_provider": "unsupported"},
        {"rag_top_k": 0},
        {"rag_top_k": 21},
        {"rag_chunk_size": 99},
        {"rag_chunk_size": 100, "rag_chunk_overlap": 100},
        {"rag_chunk_overlap": -1},
        {"sql_top_k": 0},
    ],
)
def test_invalid_configuration_is_rejected(values):
    from intellectaengine.config.settings import AppSettings

    with pytest.raises(ValidationError):
        AppSettings(_env_file=None, **values)


def test_zero_overlap_is_valid_configuration():
    from intellectaengine.config.settings import AppSettings

    assert AppSettings(_env_file=None, rag_chunk_overlap=0).rag_chunk_overlap == 0


def test_unknown_provider_has_clear_error():
    from intellectaengine.config.settings import AppSettings

    with pytest.raises(ValueError, match="Unknown provider"):
        AppSettings(_env_file=None).get_default_model("unsupported")


def test_example_environment_is_complete_and_has_no_credentials(project_root):
    from intellectaengine.config.settings import AppSettings

    example = project_root / ".env.example"
    names = {
        line.split("=", 1)[0].strip().lower()
        for line in example.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#") and "=" in line
    }
    assert names == set(AppSettings.model_fields)
    settings = AppSettings(_env_file=example)
    assert settings.google_api_key == settings.groq_api_key == settings.openai_api_key == ""


def test_blank_configured_model_is_rejected():
    from intellectaengine.config.settings import AppSettings

    with pytest.raises(ValidationError):
        AppSettings(_env_file=None, default_ollama_model=" ")


def test_settings_diagnostics_hide_input_and_credentials():
    from intellectaengine.config.settings import AppSettings

    config = AppSettings(_env_file=None, google_api_key="SYNTHETIC-KEY")
    assert "SYNTHETIC-KEY" not in repr(config)
    with pytest.raises(ValidationError) as failure:
        AppSettings(_env_file=None, default_llm_provider="SYNTHETIC-KEY")
    assert "SYNTHETIC-KEY" not in str(failure.value)


@pytest.mark.parametrize(
    "values",
    [
        {"sql_top_k": 1001},
        {"sql_cell_char_limit": 31},
        {"sql_observation_char_limit": 127},
        {"sql_statement_seconds": 0},
        {"sql_statement_seconds": float("inf")},
        {"sql_statement_steps": 999},
        {"sql_lock_timeout_ms": 0},
        {"sql_allowed_roots": ["relative/path"]},
        {"sql_allowed_roots": [""]},
    ],
)
def test_sql_settings_reject_invalid_limits_and_roots(values):
    from intellectaengine.config.settings import AppSettings

    with pytest.raises(ValidationError):
        AppSettings(_env_file=None, **values)


def test_sql_roots_environment_is_explicit_json(monkeypatch, tmp_path):
    import json

    from intellectaengine.config.settings import AppSettings

    assert AppSettings(_env_file=None).sql_allowed_roots == []
    monkeypatch.setenv("SQL_ALLOWED_ROOTS", json.dumps([str(tmp_path)]))
    assert AppSettings(_env_file=None).sql_allowed_roots == [str(tmp_path)]


@pytest.mark.parametrize(
    "values",
    [
        {"web_search_max_results": 0},
        {"web_search_max_results": 21},
        {"web_scrape_timeout": 0},
        {"web_scrape_timeout": 61},
        {"web_query_char_limit": 0},
        {"web_query_char_limit": 10001},
        {"web_url_char_limit": 127},
        {"web_url_char_limit": 8193},
        {"web_observation_char_limit": 127},
        {"web_observation_char_limit": 100001},
        {"web_response_byte_limit": 0},
        {"web_response_byte_limit": 2000001},
        {"web_elapsed_seconds": 0},
        {"web_elapsed_seconds": 121},
        {"web_elapsed_seconds": float("inf")},
        {"web_elapsed_seconds": float("nan")},
    ],
)
def test_web_settings_reject_invalid_limits(values):
    from intellectaengine.config.settings import AppSettings

    with pytest.raises(ValidationError):
        AppSettings(_env_file=None, **values)


def test_web_environment_limits(monkeypatch):
    from intellectaengine.config.settings import AppSettings

    monkeypatch.setenv("WEB_SEARCH_MAX_RESULTS", "2")
    monkeypatch.setenv("WEB_RESPONSE_BYTE_LIMIT", "128")
    monkeypatch.setenv("WEB_ELAPSED_SECONDS", "2.5")
    config = AppSettings(_env_file=None)
    assert config.web_search_max_results == 2
    assert config.web_response_byte_limit == 128
    assert config.web_elapsed_seconds == 2.5
