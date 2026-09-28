"""Headless dispatch and real offline executor contracts."""

from types import SimpleNamespace

import pytest


def fail(*args, **kwargs):
    raise RuntimeError("token=SYNTHETIC-KEY postgresql://user:password@host/private private-query")


def forbidden(*args, **kwargs):
    pytest.fail("Unnecessary provider creation")


@pytest.mark.parametrize("mode", ["auto", "rag", "sql", "web", "chat"])
def test_headless_modes_do_not_touch_session_state_or_history(monkeypatch, mode):
    import streamlit as st
    from langchain_core.language_models.fake import FakeListLLM
    from langchain_core.documents import Document

    from intellectaengine.core.application import ApplicationService
    from intellectaengine.core.contracts import AgentContext
    from intellectaengine.tools.rag_tool import RAGTool
    from intellectaengine.tools.sql_tool import SQLTool
    from intellectaengine.tools.web_research_tool import WebResearchTool

    class NoSession:
        def __getattribute__(self, name):
            pytest.fail("Headless execution touched Streamlit session state")

    monkeypatch.setattr(st, "session_state", NoSession())
    store = SimpleNamespace(
        as_retriever=lambda **_: SimpleNamespace(
            invoke=lambda q: [Document(page_content="evidence")]
        )
    )
    context = AgentContext(vector_store=store, db_uri="USE_SAMPLE_DB")
    context.memory.replace_from_transcript(
        [{"role": "user", "content": "before"}, {"role": "assistant", "content": "prior"}]
    )
    monkeypatch.setattr(
        RAGTool, "_build_chain", lambda **kw: SimpleNamespace(invoke=lambda q: {"answer": "reply"})
    )
    monkeypatch.setattr(SQLTool, "_connect", lambda uri: SimpleNamespace())
    monkeypatch.setattr(
        SQLTool, "_build_agent", lambda **kw: SimpleNamespace(invoke=lambda q: {"output": "reply"})
    )
    monkeypatch.setattr(WebResearchTool, "search", lambda q: "reply")
    model = FakeListLLM(responses=["Final Answer: reply" if mode == "auto" else "reply"])
    result = ApplicationService.run(
        "question",
        "ollama",
        context=context,
        mode=mode,
        llm_factory=forbidden if mode == "web" else lambda **kw: model,
    )
    assert result.ok and result.error is None and result.answer == "reply"
    assert [m.content for m in context.memory.get_history()] == ["before", "prior"]


def test_application_import_is_independent_of_streamlit(monkeypatch):
    import os
    import subprocess
    import sys

    monkeypatch.delenv("PYTHONPATH", raising=False)
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            "import intellectaengine.core.application; import sys; assert 'streamlit' not in sys.modules",
        ],
        env=os.environ.copy(),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("mode", ["rag", "sql"])
def test_missing_resources_precede_provider_creation(mode):
    from intellectaengine.core.application import ApplicationService
    from intellectaengine.core.contracts import ErrorCode

    result = ApplicationService.run("question", "unsupported", mode=mode, llm_factory=forbidden)
    assert result.error == ErrorCode.MISSING_RESOURCE


def test_missing_sample_database_precedes_provider_creation(monkeypatch, tmp_path):
    import intellectaengine.core.sql_policy as sql
    from intellectaengine.core.application import ApplicationService
    from intellectaengine.core.contracts import AgentContext, ErrorCode

    monkeypatch.setattr(sql, "CHINOOK_DB_RESOURCE", tmp_path / "absent.db")
    result = ApplicationService.run(
        "question",
        "ollama",
        mode="sql",
        context=AgentContext(db_uri="USE_SAMPLE_DB"),
        llm_factory=forbidden,
    )
    assert result.error == ErrorCode.MISSING_RESOURCE


@pytest.mark.parametrize("mode,query", [("unsupported", "q"), ("auto", " "), ("web", "")])
def test_invalid_requests_do_not_create_providers(mode, query):
    from intellectaengine.core.application import ApplicationService
    from intellectaengine.core.contracts import ErrorCode

    assert (
        ApplicationService.run(query, "ollama", mode=mode, llm_factory=forbidden).error
        == ErrorCode.INVALID_CONFIGURATION
    )


@pytest.mark.parametrize("mode", ["auto", "chat", "rag", "sql"])
def test_provider_initialization_failure_is_safe(mode, caplog):
    from intellectaengine.core.application import ApplicationService
    from intellectaengine.core.contracts import AgentContext, ErrorCode

    result = ApplicationService.run(
        "private-query",
        "ollama",
        mode=mode,
        context=AgentContext(vector_store=object(), db_uri="USE_SAMPLE_DB"),
        llm_factory=fail,
    )
    assert result.error == ErrorCode.PROVIDER_FAILURE
    for secret in ["SYNTHETIC-KEY", "password", "postgresql://", "private-query"]:
        assert secret not in repr(result) + caplog.text


@pytest.mark.parametrize("automatic", [False, True])
@pytest.mark.parametrize(
    "tool_name,mode",
    [
        ("general_chat", "chat"),
        ("rag_document_search", "rag"),
        ("sql_database_query", "sql"),
        ("web_research", "web"),
    ],
)
def test_actual_tool_failures_abort_both_paths(monkeypatch, automatic, tool_name, mode, caplog):
    from langchain_core.language_models.fake import FakeListLLM
    from langchain_core.documents import Document

    import intellectaengine.tools.web_research_tool as web
    from intellectaengine.core.application import ApplicationService
    from intellectaengine.core.contracts import AgentContext, ErrorCode
    from intellectaengine.tools.rag_tool import RAGTool
    from intellectaengine.tools.sql_tool import SQLTool

    monkeypatch.setattr(RAGTool, "_build_chain", fail)
    monkeypatch.setattr(SQLTool, "_connect", fail)
    monkeypatch.setattr(web, "DDGS", fail)
    responses = [
        f"Action: {tool_name}\nAction Input: private-query",
        "Final Answer: hidden failure",
    ]
    model = FakeListLLM(responses=responses)
    original = type(model)._call
    calls = []

    def call(self, prompt, **kw):
        calls.append(prompt)
        if mode == "chat" and (not automatic or len(calls) == 2):
            fail()
        return original(self, prompt, **kw)

    monkeypatch.setattr(type(model), "_call", call)
    store = SimpleNamespace(
        as_retriever=lambda **_: SimpleNamespace(
            invoke=lambda q: [Document(page_content="evidence")]
        )
    )
    result = ApplicationService.run(
        "private-query",
        "ollama",
        mode="auto" if automatic else mode,
        context=AgentContext(vector_store=store, db_uri="USE_SAMPLE_DB"),
        llm_factory=lambda **kw: model,
    )
    assert not result.ok
    assert result.error == (
        ErrorCode.PROVIDER_FAILURE if mode == "chat" else ErrorCode.TOOL_FAILURE
    )
    assert result.tool_used == tool_name
    assert "hidden failure" not in result.answer
    assert len(calls) == (
        2 if automatic and mode == "chat" else 1 if automatic or mode == "chat" else 0
    )
    for secret in ["SYNTHETIC-KEY", "password", "postgresql://", "private-query"]:
        assert secret not in repr(result) + caplog.text


@pytest.mark.parametrize("boundary", ["_build_tools", "create_react_agent", "invoke"])
def test_router_construction_and_execution_failures(monkeypatch, boundary):
    from langchain_core.language_models.fake import FakeListLLM

    import intellectaengine.core.router_agent as router
    from intellectaengine.core.contracts import ErrorCode

    target = (
        router.RouterAgent
        if boundary == "_build_tools"
        else router.BoundedAgentExecutor
        if boundary == "invoke"
        else router
    )
    monkeypatch.setattr(target, boundary, fail)
    result = router.RouterAgent.run(
        "q", "ollama", llm_factory=lambda **kw: FakeListLLM(responses=["unused"])
    )
    assert result.error == ErrorCode.EXECUTION_FAILURE


def test_local_prompt_and_real_react_execution(monkeypatch):
    from langchain_core.callbacks import BaseCallbackHandler
    from langchain_core.language_models.fake import FakeListLLM

    from intellectaengine.core.application import ApplicationService
    from intellectaengine.core.prompts import router_prompt
    from intellectaengine.tools.web_research_tool import WebResearchTool

    assert set(router_prompt().input_variables) == {
        "tools",
        "tool_names",
        "agent_scratchpad",
        "chat_history",
        "input",
    }
    prompts = []

    class Recorder(BaseCallbackHandler):
        def on_llm_start(self, serialized, incoming, **kwargs):
            prompts.extend(incoming)

    model = FakeListLLM(
        responses=["Action: web_research\nAction Input: rewritten", "Final Answer: final"],
        callbacks=[Recorder()],
    )
    queries = []

    def web(query):
        queries.append(query)
        return "observation"

    monkeypatch.setattr(WebResearchTool, "run", web)
    result = ApplicationService.run("original", "ollama", llm_factory=lambda **kw: model)
    assert result.ok and result.answer == "final" and result.tool_used == "web_research"
    assert queries == ["rewritten"]
    assert len(prompts) == 2 and "observation" in prompts[-1]
    assert "rag_document_search" not in prompts[0] and "sql_database_query" not in prompts[0]


def test_iteration_exhaustion_is_explicit(monkeypatch):
    from langchain_core.language_models.fake import FakeListLLM

    from intellectaengine.core.application import ApplicationService
    from intellectaengine.core.contracts import ErrorCode
    from intellectaengine.tools.web_research_tool import WebResearchTool

    calls = []
    monkeypatch.setattr(WebResearchTool, "run", lambda query: calls.append(query) or "observation")
    model = FakeListLLM(responses=["Action: web_research\nAction Input: again"])
    result = ApplicationService.run("q", "ollama", llm_factory=lambda **kw: model)
    assert result.error == ErrorCode.EXECUTION_LIMIT
    assert len(calls) == 6


def test_execution_time_budget_is_explicit(monkeypatch):
    from langchain_core.language_models.fake import FakeListLLM

    from intellectaengine.core.contracts import ApplicationError, ErrorCode
    from intellectaengine.core.execution import BoundedAgentExecutor
    from intellectaengine.core.prompts import router_prompt
    from langchain_classic.agents import create_react_agent

    agent = create_react_agent(FakeListLLM(responses=["unused"]), [], router_prompt())
    executor = BoundedAgentExecutor(agent=agent, tools=[], max_execution_time=60)
    with pytest.raises(ApplicationError) as failure:
        executor._should_continue(0, 61)
    assert failure.value.code == ErrorCode.EXECUTION_LIMIT


def test_interrupt_does_not_become_a_final_result():
    from intellectaengine.core.application import ApplicationService

    def interrupt(**kw):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        ApplicationService.run("q", "ollama", llm_factory=interrupt)


@pytest.mark.parametrize(
    "response,code",
    [
        ("Action: unavailable_tool\nAction Input: q", "tool_failure"),
        ("malformed private-query response", "execution_failure"),
        ("Final Answer: ", "execution_failure"),
    ],
)
def test_invalid_agent_outputs_cannot_be_success(response, code):
    from langchain_core.language_models.fake import FakeListLLM

    from intellectaengine.core.application import ApplicationService

    model = FakeListLLM(responses=[response, "Final Answer: misleading success"])
    result = ApplicationService.run("q", "ollama", llm_factory=lambda **kw: model)
    assert result.error == code
    assert "private-query" not in result.answer
    assert "misleading success" not in result.answer


@pytest.mark.parametrize("failure", ["timeout", "http", "empty"])
def test_scrape_errors_are_typed_and_safe(web_network, failure):
    import requests

    from intellectaengine.core.application import ApplicationService
    from intellectaengine.core.contracts import ErrorCode

    if failure == "timeout":
        web_network.failure = requests.exceptions.Timeout("SYNTHETIC-KEY")
    elif failure == "http":
        web_network.status = 500
        web_network.body = b"SYNTHETIC-KEY"
    else:
        web_network.body = b""
    result = ApplicationService.run(
        "SCRAPE:https://example.com/?secret=SYNTHETIC-KEY", "unknown", mode="web"
    )
    assert result.error == ErrorCode.TOOL_FAILURE
    assert "SYNTHETIC-KEY" not in result.answer
    assert web_network.adapter_closes == 1
