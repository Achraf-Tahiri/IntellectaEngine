"""Exercise actual Streamlit dispatch, router/executor, and sidebar boundaries offline."""

import pytest


MODES = {
    "auto": "auto",
    "rag": "rag",
    "sql": "sql",
    "web": "web",
    "chat": "chat",
}


@pytest.fixture
def app(project_root):
    from streamlit.testing.v1 import AppTest

    result = AppTest.from_file(str(project_root / "app.py")).run(timeout=60)
    assert not result.exception
    return result


@pytest.fixture
def fake_model(monkeypatch):
    from langchain_core.callbacks import BaseCallbackHandler
    from langchain_core.language_models.fake import FakeListLLM

    from intellectaengine.core.llm_factory import LLMFactory

    prompts = []

    class Recorder(BaseCallbackHandler):
        def on_llm_start(self, serialized, incoming, **kwargs):
            prompts.extend(incoming)

    def install(responses):
        model = FakeListLLM(responses=responses, callbacks=[Recorder()])
        monkeypatch.setattr(LLMFactory, "create", lambda **kwargs: model)
        return prompts

    return install


def assert_history(app, expected):
    from intellectaengine.ui.session_state import SessionStateManager as K

    assert not app.exception
    transcript = app.session_state[K.KEY_CHAT_MESSAGES]
    assert [message["content"] for message in transcript] == expected
    assert [message["role"] for message in transcript] == ["user", "assistant"] * (
        len(expected) // 2
    )
    assert [message.content for message in app.session_state[K.KEY_MEMORY].get_history()] == (
        expected[-20:]
    )


def submit(app, query):
    app.chat_input[0].set_value(query).run(timeout=60)
    assert not app.exception


def button(app, label):
    return next(item for item in app.button if item.label == label)


@pytest.mark.parametrize("mode", MODES)
def test_all_modes_commit_final_turn_once(app, fake_model, monkeypatch, mode):
    from intellectaengine.tools.rag_tool import RAGTool
    from intellectaengine.tools.sql_tool import SQLTool
    from intellectaengine.tools.web_research_tool import WebResearchTool
    from intellectaengine.ui.session_state import SessionStateManager as K

    if mode == "auto":
        responses = [
            "Thought: Use chat.\nAction: general_chat\nAction Input: rewritten internal query",
            "intermediate tool observation",
            "Thought: Done.\nFinal Answer: final reply",
        ]
    else:
        responses = ["final reply"]
    prompts = fake_model(responses)
    calls = []

    def tool(**kwargs):
        calls.append(kwargs["query"])
        if kwargs.get("return_result"):
            from intellectaengine.tools.rag_tool import RAGAnswer

            return RAGAnswer("final reply", ())
        return "final reply"

    monkeypatch.setattr(RAGTool, "run", tool)
    monkeypatch.setattr(SQLTool, "run", tool)
    monkeypatch.setattr(WebResearchTool, "run", tool)
    if mode == "rag":
        app.session_state[K.KEY_VECTOR_STORE] = object()
    if mode == "sql":
        app.session_state[K.KEY_DB_CONNECTED] = True
        app.session_state[K.KEY_DB_URI] = "USE_SAMPLE_DB"
    app.selectbox(key=K.KEY_AGENT_MODE).set_value(MODES[mode]).run()
    submit(app, "original question")
    assert_history(app, ["original question", "final reply"])
    app.run()  # A Streamlit rerun must not replay or duplicate a committed request.
    assert_history(app, ["original question", "final reply"])
    if mode == "auto":
        assert len(prompts) == 3  # Real ReAct executor and real ChatTool were used.
        assert "intermediate tool observation" in prompts[-1]
    elif mode in {"rag", "sql", "web"}:
        assert calls == ["original question"]
    # Switching to chat must see the final answer from every previous mode.
    prompts.clear()
    fake_model(["follow-up reply"])
    app.selectbox(key=K.KEY_AGENT_MODE).set_value(MODES["chat"]).run()
    submit(app, "follow-up")
    assert "original question" in prompts[-1]
    assert "final reply" in prompts[-1]
    assert "intermediate tool observation" not in prompts[-1]
    assert "rewritten internal query" not in prompts[-1]
    assert_history(app, ["original question", "final reply", "follow-up", "follow-up reply"])


def test_sidebar_edits_and_two_real_sessions(app, project_root, fake_model):
    from streamlit.testing.v1 import AppTest

    from intellectaengine.ui.session_state import SessionStateManager as K

    prompts = fake_model(["first answer", "second answer", "after clear"])
    app.selectbox(key=K.KEY_AGENT_MODE).set_value(MODES["chat"]).run()
    submit(app, "first question")
    submit(app, "second question")
    other = AppTest.from_file(str(project_root / "app.py")).run(timeout=60)
    assert_history(other, [])
    other.selectbox(key=K.KEY_AGENT_MODE).set_value(MODES["chat"]).run()
    submit(other, "other session question")
    assert "first question" not in prompts[-1]
    assert "second question" not in prompts[-1]
    other_history = [item["content"] for item in other.session_state[K.KEY_CHAT_MESSAGES]]
    original_id = app.session_state[K.KEY_SESSION_ID]
    assert original_id != other.session_state[K.KEY_SESSION_ID]
    button(app, "Undo").click().run()
    assert_history(app, ["first question", "first answer"])
    button(app, "Clear chat").click().run()
    assert_history(app, [])
    assert app.session_state[K.KEY_SESSION_ID] == original_id
    submit(app, "fresh question")
    assert "first question" not in prompts[-1]
    assert "second question" not in prompts[-1]
    old_memory = app.session_state[K.KEY_MEMORY]
    button(app, "Reset workspace").click().run()
    assert_history(app, [])
    assert old_memory.get_history() == []
    assert app.session_state[K.KEY_SESSION_ID] != original_id
    other.run()
    assert_history(other, other_history)


@pytest.mark.parametrize(
    "failure", ["factory", "executor", "chat", "forced", "missing_rag", "missing_sql"]
)
def test_failed_requests_record_displayed_reply_once(app, fake_model, monkeypatch, failure):
    from intellectaengine.core.llm_factory import LLMFactory
    from intellectaengine.tools.web_research_tool import WebResearchTool
    from intellectaengine.ui.session_state import SessionStateManager as K

    fake_model(["unused"])

    def fail(*args, **kwargs):
        raise RuntimeError("scripted failure")

    if failure == "factory":
        monkeypatch.setattr(LLMFactory, "create", fail)
        mode = "auto"
    elif failure in {"chat", "executor"}:
        model = LLMFactory.create()
        monkeypatch.setattr(type(model), "_call", fail)
        mode = "chat" if failure == "chat" else "auto"
    elif failure == "forced":
        monkeypatch.setattr(WebResearchTool, "run", fail)
        mode = "web"
    else:
        mode = "rag" if failure == "missing_rag" else "sql"
    app.selectbox(key=K.KEY_AGENT_MODE).set_value(MODES[mode]).run()
    submit(app, "failing question")
    reply = app.session_state[K.KEY_CHAT_MESSAGES][-1]["content"]
    assert "⚠️" in reply
    assert_history(app, ["failing question", reply])
    app.run()
    assert_history(app, ["failing question", reply])
    button(app, "Undo").click().run()
    assert_history(app, [])


def test_direct_fallback_only_persists_final_ui_reply(app, fake_model, monkeypatch):
    from intellectaengine.core.router_agent import RouterAgent

    fake_model(["fallback answer"])
    monkeypatch.setattr(RouterAgent, "_build_tools", lambda **kwargs: [])
    submit(app, "fallback question")
    assert_history(app, ["fallback question", "fallback answer"])


@pytest.mark.parametrize("mode", ["auto", "chat"])
def test_model_receives_only_the_window_after_undo(app, fake_model, mode):
    from intellectaengine.ui.session_state import SessionStateManager as K

    prompts = fake_model(["reply"])
    app.selectbox(key=K.KEY_AGENT_MODE).set_value(MODES["chat"]).run()
    for number in range(12):
        submit(app, f"question-{number:02d}")
    button(app, "Undo").click().run()
    fake_model(["Final Answer: next reply" if mode == "auto" else "next reply"])
    app.selectbox(key=K.KEY_AGENT_MODE).set_value(MODES[mode]).run()
    submit(app, "next question")
    prompt = prompts[-1]
    assert "question-00" not in prompt  # Outside the window.
    assert "question-01" in prompt  # Restored from visible history by undo.
    assert "question-10" in prompt
    assert "question-11" not in prompt  # Undone.
    expected = [item for number in range(11) for item in (f"question-{number:02d}", "reply")]
    assert_history(app, [*expected, "next question", "next reply"])


def test_executor_failure_after_tool_does_not_commit_observation(app, fake_model, monkeypatch):
    from intellectaengine.core.llm_factory import LLMFactory
    from intellectaengine.ui.session_state import SessionStateManager as K

    prompts = fake_model(
        [
            "Thought: Use chat.\nAction: general_chat\nAction Input: internal question",
            "private intermediate observation",
        ]
    )
    model = LLMFactory.create()
    original_call = type(model)._call
    calls = 0

    def fail_final(self, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise RuntimeError("final generation failed")
        return original_call(self, *args, **kwargs)

    monkeypatch.setattr(type(model), "_call", fail_final)
    submit(app, "original question")
    reply = app.session_state[K.KEY_CHAT_MESSAGES][-1]["content"]
    assert "agent could not complete" in reply
    assert "final generation failed" not in reply
    assert_history(app, ["original question", reply])
    monkeypatch.setattr(type(model), "_call", original_call)
    fake_model(["recovered"])
    app.selectbox(key=K.KEY_AGENT_MODE).set_value(MODES["chat"]).run()
    submit(app, "retry")
    assert "private intermediate observation" not in prompts[-1]
    assert "internal question" not in prompts[-1]
    assert reply in prompts[-1]  # Displayed errors follow the same policy.
    assert_history(app, ["original question", reply, "retry", "recovered"])


def test_automatic_tool_failure_is_safe_and_undoable(app, fake_model, monkeypatch):
    import intellectaengine.tools.web_research_tool as web
    from intellectaengine.ui.session_state import SessionStateManager as K

    prompts = fake_model(
        [
            "Action: web_research\nAction Input: secret internal query",
            "Final Answer: misleading success",
        ]
    )

    def fail(*args, **kwargs):
        raise RuntimeError("SYNTHETIC-KEY https://user:password@host private-content")

    monkeypatch.setattr(web, "DDGS", fail)
    submit(app, "original question")
    reply = app.session_state[K.KEY_CHAT_MESSAGES][-1]["content"]
    assert "selected tool could not complete" in reply
    assert "SYNTHETIC-KEY" not in reply and "password" not in reply
    assert len(prompts) == 1  # No final synthesis that could disguise the failure.
    assert_history(app, ["original question", reply])
    app.run()
    assert_history(app, ["original question", reply])
    button(app, "Undo").click().run()
    assert_history(app, [])


@pytest.mark.parametrize("action", ["Clear", "Reset workspace"])
@pytest.mark.parametrize("failure", [None, "client", "lookup", "delete", "verification"])
def test_pdf_clear_reset_preserve_handles_until_deletion_proven(
    app, tmp_path, monkeypatch, action, failure
):
    from intellectaengine.config.settings import AppSettings
    from intellectaengine.connectors.vectorstore_connector import VectorStoreConnector as V
    from intellectaengine.core.document_ingestion import DocumentSet
    from intellectaengine.ui.session_state import SessionStateManager as K

    config = AppSettings(_env_file=None, chroma_persist_base_dir=str(tmp_path / "ui-index"))
    client = V._client(config)
    collection = client.create_collection("ui-collection", embedding_function=None)
    collection.add(ids=["one"], documents=["local evidence"], embeddings=[[1.0, 0.0]])
    active = DocumentSet(
        "ui-collection",
        app.session_state[K.KEY_SESSION_ID],
        "batch",
        "config",
        "huggingface",
        "fake",
        (),
    )
    app.session_state[K.KEY_DOCUMENT_SET] = active
    app.session_state[K.KEY_VECTOR_STORE] = "active-handle"
    app.session_state[K.KEY_PDF_NAMES] = ["evidence.pdf"]
    original_session = app.session_state[K.KEY_SESSION_ID]
    lookup = client.get_collection
    delete = client.delete_collection
    lookups = 0

    def unavailable(*args, **kwargs):
        raise RuntimeError("SYNTHETIC-SECRET private storage")

    def get(name):
        nonlocal lookups
        lookups += 1
        if failure == "lookup" or (failure == "verification" and lookups == 2):
            unavailable()
        return lookup(name)

    with monkeypatch.context() as patch:
        patch.setattr(V, "_client", unavailable if failure == "client" else lambda config: client)
        patch.setattr(client, "get_collection", get)
        patch.setattr(client, "delete_collection", unavailable if failure == "delete" else delete)
        button(app, action).click().run()
    assert not app.exception
    if failure:
        assert app.session_state[K.KEY_DOCUMENT_SET] == active
        assert app.session_state[K.KEY_VECTOR_STORE] == "active-handle"
        assert app.session_state[K.KEY_PDF_NAMES] == ["evidence.pdf"]
        assert app.session_state[K.KEY_SESSION_ID] == original_session
        assert app.error and not app.toast
        assert "SYNTHETIC-SECRET" not in str(app.error)
        monkeypatch.setattr(V, "_client", lambda config: client)
        button(app, action).click().run()
    assert not app.exception
    assert app.session_state[K.KEY_DOCUMENT_SET] is None
    assert app.session_state[K.KEY_VECTOR_STORE] is None
    assert app.session_state[K.KEY_PDF_NAMES] == []
    assert client.list_collections() == []
    if action == "Reset workspace":
        assert app.session_state[K.KEY_SESSION_ID] != original_session


@pytest.mark.parametrize("mode", ["auto", "web"])
@pytest.mark.parametrize("scrape", [False, True])
@pytest.mark.parametrize("failure", [False, True])
def test_real_web_boundaries_commit_once_and_undo(
    app, fake_model, monkeypatch, web_network, web_search, mode, scrape, failure, caplog
):
    from intellectaengine.core.llm_factory import LLMFactory
    from intellectaengine.ui.session_state import SessionStateManager as K

    query = "SCRAPE:https://example.com/page" if scrape else "offline search"
    if failure:
        web_network.read_failure = RuntimeError("SYNTHETIC-SECRET")
        web_search.failure = RuntimeError("SYNTHETIC-SECRET")
    if mode == "auto":
        prompts = fake_model(
            [
                f"Action: web_research\nAction Input: {query}",
                "Final Answer: researched answer",
            ]
        )
    else:

        def forbidden(**kwargs):
            pytest.fail("Forced web constructed an LLM")

        monkeypatch.setattr(LLMFactory, "create", forbidden)
    app.selectbox(key=K.KEY_AGENT_MODE).set_value(MODES[mode]).run()
    submit(app, query)
    transcript = app.session_state[K.KEY_CHAT_MESSAGES]
    answer = transcript[-1]["content"]
    assert_history(app, [query, answer])
    if failure:
        assert answer.startswith("⚠️") and "SYNTHETIC-SECRET" not in answer + caplog.text
    elif mode == "auto":
        assert answer == "researched answer"
        assert "untrusted evidence" in prompts[-1]
        assert ("Offline page evidence" if scrape else "Offline snippet") in prompts[-1]
    else:
        assert ("Offline page evidence" if scrape else "Offline snippet") in answer
    if mode == "auto":
        assert len(prompts) == (1 if failure else 2)  # Fail fast, without a repair step.
    assert web_network.adapter_closes == (1 if scrape else 0)
    assert web_search.closed == (0 if scrape else 1)
    app.run()
    assert_history(app, [query, answer])
    button(app, "Undo").click().run()
    assert_history(app, [])
