import importlib

import pytest


@pytest.mark.integration
def test_application_imports_without_credentials_or_network():
    app = importlib.import_module("intellectaengine.streamlit_app")
    assert callable(app.main)


@pytest.mark.integration
@pytest.mark.parametrize(
    ("module", "symbol"),
    [
        ("langchain_google_genai", "ChatGoogleGenerativeAI"),
        ("langchain_google_genai", "GoogleGenerativeAIEmbeddings"),
        ("langchain_groq", "ChatGroq"),
        ("langchain_openai", "ChatOpenAI"),
        ("langchain_ollama", "ChatOllama"),
        ("sentence_transformers", "SentenceTransformer"),
        ("fastembed", "TextEmbedding"),
    ],
)
def test_provider_dependencies_import_without_downloading_models(module, symbol):
    assert callable(getattr(importlib.import_module(module), symbol))


@pytest.mark.integration
def test_streamlit_initial_render_without_credentials(project_root):
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(project_root / "app.py")).run(timeout=60)
    assert not app.exception
    assert len(app.chat_input) == 1
    assert any("GOOGLE_API_KEY" in warning.value for warning in app.warning)
