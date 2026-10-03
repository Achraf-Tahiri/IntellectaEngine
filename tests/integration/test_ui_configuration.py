"""Real widgets honor settings, preserve custom selections, and reset safely."""


def test_environment_defaults_provider_switch_and_reset(project_root, monkeypatch):
    from streamlit.testing.v1 import AppTest

    import intellectaengine.ui.session_state as session
    import intellectaengine.ui.sidebar as sidebar
    from intellectaengine.config.settings import AppSettings

    monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "ollama")
    monkeypatch.setenv("DEFAULT_OLLAMA_MODEL", "local-custom:1")
    monkeypatch.setenv("DEFAULT_OPENAI_MODEL", "configured-custom")
    monkeypatch.setenv("DEFAULT_EMBEDDING_PROVIDER", "fastembed")
    config = AppSettings(_env_file=None)
    monkeypatch.setattr(session, "settings", config)
    monkeypatch.setattr(sidebar, "settings", config)
    k = session.SessionStateManager
    app = AppTest.from_file(str(project_root / "app.py")).run(timeout=60)
    assert not app.exception
    assert app.session_state[k.KEY_LLM_PROVIDER] == "ollama"
    assert app.session_state[k.KEY_LLM_MODEL] == "local-custom:1"
    assert app.session_state[k.KEY_EMBEDDING_PROVIDER] == "fastembed"
    app.text_input(key=k.KEY_LLM_MODEL).set_value("deliberate-custom").run()
    app.run()
    assert app.session_state[k.KEY_LLM_MODEL] == "deliberate-custom"
    app.selectbox(key=k.KEY_LLM_PROVIDER).set_value("openai").run()
    assert not app.exception
    assert app.session_state[k.KEY_LLM_MODEL] == "configured-custom"
    app.text_input(key=k.KEY_LLM_MODEL).set_value("another-custom").run()
    app.run()
    assert app.session_state[k.KEY_LLM_MODEL] == "another-custom"
    app.selectbox(key=k.KEY_LLM_PROVIDER).set_value("ollama").run()
    assert app.session_state[k.KEY_LLM_MODEL] == "local-custom:1"
    app.selectbox(key=k.KEY_EMBEDDING_PROVIDER).set_value("huggingface").run()
    app.text_input(key=k.KEY_LLM_MODEL).set_value("edited-local").run()
    next(b for b in app.button if b.label == "Reset workspace").click().run()
    assert not app.exception
    assert app.session_state[k.KEY_LLM_PROVIDER] == "ollama"
    assert app.session_state[k.KEY_LLM_MODEL] == "local-custom:1"
    assert app.session_state[k.KEY_EMBEDDING_PROVIDER] == "fastembed"


def test_forced_web_ui_needs_no_model_or_credentials(project_root, monkeypatch, web_search):
    from streamlit.testing.v1 import AppTest

    from intellectaengine.core.llm_factory import LLMFactory
    from intellectaengine.ui.session_state import SessionStateManager as K

    def forbidden(**kwargs):
        raise AssertionError("LLM must not be constructed")

    monkeypatch.setattr(LLMFactory, "create", forbidden)
    web_search.results = []
    app = AppTest.from_file(str(project_root / "app.py")).run(timeout=60)
    app.text_input(key=K.KEY_LLM_MODEL).set_value("").run()
    app.selectbox(key=K.KEY_AGENT_MODE).set_value("web").run()
    assert not app.chat_input[0].disabled
    app.chat_input[0].set_value("question").run()
    assert not app.exception
    assert [m["content"] for m in app.session_state[K.KEY_CHAT_MESSAGES]] == [
        "question",
        "No web search results found.",
    ]


def test_sql_uri_masked_and_failed_connection_preserves_prior_state(
    project_root, monkeypatch, caplog
):
    from streamlit.testing.v1 import AppTest

    from intellectaengine.connectors.database_connector import DatabaseConnector
    from intellectaengine.ui.session_state import SessionStateManager as K

    app = AppTest.from_file(str(project_root / "app.py")).run(timeout=60)
    next(c for c in app.checkbox if c.label == "Use Chinook sample database").check().run()
    next(b for b in app.button if b.label == "Connect").click().run()
    assert app.session_state[K.KEY_DB_CONNECTED]
    tables = app.session_state[K.KEY_DB_TABLES]
    assert "Artist" in tables
    next(c for c in app.checkbox if c.label == "Use Chinook sample database").uncheck().run()
    uri = next(t for t in app.text_input if t.label == "Database URI")
    assert uri.proto.type == uri.proto.PASSWORD
    uri.set_value("postgresql://user:SYNTHETIC-SECRET@host/db").run()
    next(b for b in app.button if b.label == "Connect").click().run()
    assert app.session_state[K.KEY_DB_URI] == "USE_SAMPLE_DB"
    assert app.session_state[K.KEY_DB_CONNECTED]
    assert app.session_state[K.KEY_DB_TABLES] == tables
    assert "SYNTHETIC-SECRET" not in str([e.value for e in app.error]) + caplog.text

    def fail(*args):
        raise RuntimeError("SYNTHETIC-SECRET schema failure")

    monkeypatch.setattr(DatabaseConnector, "get_table_names", fail)
    next(b for b in app.button if b.label == "Connect").click().run()
    assert not app.exception
    assert app.session_state[K.KEY_DB_URI] == "USE_SAMPLE_DB"
    assert app.session_state[K.KEY_DB_TABLES] == tables
    assert "SYNTHETIC-SECRET" not in str([e.value for e in app.error]) + caplog.text


def test_example_prompt_is_a_draft_until_explicit_submission(project_root, monkeypatch):
    from streamlit.testing.v1 import AppTest

    from intellectaengine.core.application import ApplicationService
    from intellectaengine.core.contracts import AgentResult
    from intellectaengine.ui.session_state import SessionStateManager as K

    calls = []

    def run(**kwargs):
        calls.append(kwargs)
        return AgentResult(answer="Example response", tool_used="chat_direct")

    monkeypatch.setattr(ApplicationService, "run", run)
    app = AppTest.from_file(str(project_root / "app.py")).run(timeout=60)
    prompt = next(b for b in app.button if b.key == "prompt_1_1")
    text = prompt.label
    prompt.click().run()
    assert not app.exception
    assert calls == []
    assert app.session_state[K.KEY_CHAT_MESSAGES] == []
    assert app.chat_input[0].proto.value == text
    app.chat_input[0].set_value(text + " Keep it brief.").run()
    assert not app.exception
    app.run()
    assert len(calls) == 1
    assert calls[0]["query"] == text + " Keep it brief."
    assert len(app.session_state[K.KEY_CHAT_MESSAGES]) == 2
    next(b for b in app.button if b.label == "Clear chat").click().run()
    assert not app.exception
    assert app.session_state[K.KEY_CHAT_MESSAGES] == []
    assert not app.chat_input[0].proto.value
