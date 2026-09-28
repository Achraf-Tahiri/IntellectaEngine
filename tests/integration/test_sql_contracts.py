"""Exercise the actual SQL executor/toolkit on the bundled local sample."""

import pytest


@pytest.mark.parametrize(
    "query,expected",
    [
        ("SELECT COUNT(*) FROM Artist", None),
        ("SELECT * FROM nonexistent_table", "tool_failure"),
    ],
)
def test_sql_toolkit_failures_cannot_be_hidden_by_final_answer(query, expected):
    from langchain_core.callbacks import BaseCallbackHandler
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.messages import AIMessage

    from intellectaengine.core.application import ApplicationService
    from intellectaengine.core.contracts import AgentContext

    messages = []

    class Recorder(BaseCallbackHandler):
        def on_chat_model_start(self, serialized, incoming, **kwargs):
            messages.extend(incoming)

    class ToolModel(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    model = ToolModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{"name": "sql_db_query", "args": {"query": query}, "id": "query-1"}],
            ),
            AIMessage(content="There are 275 artists."),
        ],
        callbacks=[Recorder()],
    )
    result = ApplicationService.run(
        "How many artists?",
        "ollama",
        mode="sql",
        context=AgentContext(db_uri="USE_SAMPLE_DB"),
        llm_factory=lambda **kw: model,
    )
    assert result.error == expected
    if expected is None:
        assert result.answer == "There are 275 artists."
        assert len(messages) == 2
        assert any(message.type == "tool" and "275" in message.content for message in messages[-1])
    else:
        assert not result.ok and len(messages) == 1
        assert "nonexistent_table" not in result.answer


@pytest.mark.parametrize("missing_method", [False, True])
def test_sql_requires_explicit_tool_binding(missing_method):
    from langchain_core.language_models.fake import FakeListLLM
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.messages import AIMessage

    from intellectaengine.core.application import ApplicationService
    from intellectaengine.core.contracts import AgentContext, ErrorCode

    model = (
        FakeListLLM(responses=["unused"])
        if missing_method
        else FakeMessagesListChatModel(responses=[AIMessage(content="unused")])
    )
    result = ApplicationService.run(
        "q",
        "ollama",
        mode="sql",
        context=AgentContext(db_uri="USE_SAMPLE_DB"),
        llm_factory=lambda **kw: model,
    )
    assert result.error == ErrorCode.UNSUPPORTED_CAPABILITY


def test_sql_executor_limit_is_a_failure():
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.messages import AIMessage

    from intellectaengine.core.application import ApplicationService
    from intellectaengine.core.contracts import AgentContext, ErrorCode

    class ToolModel(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    model = ToolModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "sql_db_list_tables", "args": {"tool_input": ""}, "id": "again"}
                ],
            )
        ]
    )
    result = ApplicationService.run(
        "q",
        "ollama",
        mode="sql",
        context=AgentContext(db_uri="USE_SAMPLE_DB"),
        llm_factory=lambda **kw: model,
    )
    assert result.error == ErrorCode.EXECUTION_LIMIT
