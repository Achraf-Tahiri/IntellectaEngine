"""Regression coverage for ownership, retention, and conversation edits."""

import gc
import weakref
from uuid import UUID

import pytest


@pytest.fixture
def session(monkeypatch):
    import streamlit as st

    from intellectaengine.ui.session_state import SessionStateManager

    state = {}
    monkeypatch.setattr(st, "session_state", state)
    SessionStateManager.initialise()
    return SessionStateManager, state


def contents(memory):
    return [message.content for message in memory.get_history()]


def test_defaults_and_memory_are_independent_between_sessions(session, monkeypatch):
    import streamlit as st

    manager, first = session
    manager.complete_turn("private question", "private answer")
    for key in (manager.KEY_PDF_FILES, manager.KEY_PDF_NAMES, manager.KEY_DB_TABLES):
        first[key].append("private")
    second = {}
    monkeypatch.setattr(st, "session_state", second)
    manager.initialise()
    assert first[manager.KEY_MEMORY] is not second[manager.KEY_MEMORY]
    for key, default in manager._DEFAULTS.items():
        if isinstance(default, list):
            assert second[key] == []
            assert second[key] is not first[key]
            assert default == []
    assert contents(second[manager.KEY_MEMORY]) == []
    assert contents(first[manager.KEY_MEMORY]) == ["private question", "private answer"]
    assert first[manager.KEY_SESSION_ID] != second[manager.KEY_SESSION_ID]
    for state in (first, second):
        assert str(UUID(state[manager.KEY_SESSION_ID], version=4)) == state[manager.KEY_SESSION_ID]
    memory = second[manager.KEY_MEMORY]
    manager.initialise()
    assert second[manager.KEY_MEMORY] is memory


def test_clear_undo_and_reset_update_both_histories(session):
    manager, state = session
    memory = state[manager.KEY_MEMORY]
    old_id = state[manager.KEY_SESSION_ID]
    assert not manager.undo_last_message()
    manager.complete_turn("one", "first", "general_chat")
    manager.complete_turn("two", "second", "web_research")
    assert manager.undo_last_message()
    assert contents(memory) == ["one", "first"]
    assert state[manager.KEY_ACTIVE_TOOL] == "general_chat"
    manager.reset_chat()
    assert state[manager.KEY_CHAT_MESSAGES] == []
    assert contents(memory) == []
    assert state[manager.KEY_SESSION_ID] == old_id
    assert state[manager.KEY_ACTIVE_TOOL] == "—"
    manager.complete_turn("new", "reply")
    manager.reset_all()
    assert state[manager.KEY_CHAT_MESSAGES] == []
    assert contents(memory) == []  # Erased even for a caller retaining the old store.
    assert state[manager.KEY_MEMORY] is not memory
    assert state[manager.KEY_SESSION_ID] != old_id
    manager.reset_all()
    assert contents(state[manager.KEY_MEMORY]) == []


def test_window_is_bounded_and_undo_restores_the_correct_tail(session):
    from intellectaengine.core.memory_store import MemoryStore

    manager, state = session
    memory = state[manager.KEY_MEMORY] = MemoryStore(window_k=2)
    for number in range(5):
        manager.complete_turn(f"q{number}", f"a{number}")
    assert contents(memory) == ["q3", "a3", "q4", "a4"]
    assert len(memory._messages) == 4  # Storage, not only reads, is bounded.
    assert len(state[manager.KEY_CHAT_MESSAGES]) == 10
    snapshot = memory.get_history()
    snapshot[0].content = "tampered"
    snapshot.clear()
    assert contents(memory) == ["q3", "a3", "q4", "a4"]
    assert memory.get_formatted_history() == "Human: q3\nAI: a3\nHuman: q4\nAI: a4"
    manager.undo_last_message()
    assert contents(memory) == ["q2", "a2", "q3", "a3"]
    for _ in range(4):
        assert manager.undo_last_message()
    assert contents(memory) == []
    assert not manager.undo_last_message()


def test_zero_window_disables_model_history(session):
    from intellectaengine.core.memory_store import MemoryStore

    manager, state = session
    state[manager.KEY_MEMORY] = MemoryStore(window_k=0)
    manager.complete_turn("q", "a")
    assert contents(state[manager.KEY_MEMORY]) == []
    assert len(state[manager.KEY_CHAT_MESSAGES]) == 2


@pytest.mark.parametrize("window", [-1, True, 1.5])
def test_invalid_window_is_rejected(window):
    from intellectaengine.core.memory_store import MemoryStore

    with pytest.raises(ValueError, match="non-negative integer"):
        MemoryStore(window_k=window)


def test_memory_lifetime_follows_its_owner(session):
    manager, state = session
    manager.complete_turn("q", "a")
    reference = weakref.ref(state[manager.KEY_MEMORY])
    manager.reset_all()
    gc.collect()
    assert reference() is None
    reference = weakref.ref(state[manager.KEY_MEMORY])
    state.clear()  # Session released by its host, without a process-wide registry.
    gc.collect()
    assert reference() is None


def test_context_defaults_do_not_share_memory():
    from intellectaengine.core.router_agent import AgentContext

    first, second = AgentContext(), AgentContext()
    assert first.memory is not second.memory
    assert first.session_id != second.session_id


def test_ui_interruption_commits_nothing(session, monkeypatch):
    from contextlib import nullcontext

    import streamlit as st

    from intellectaengine.core.application import ApplicationService
    from intellectaengine.ui.chat_interface import ChatInterface

    manager, state = session
    manager.complete_turn("before", "answer")

    def interrupt(**kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(ApplicationService, "run", interrupt)
    monkeypatch.setattr(st, "chat_input", lambda **kw: "interrupted question")
    monkeypatch.setattr(st, "chat_message", lambda *a, **kw: nullcontext())
    monkeypatch.setattr(st, "spinner", lambda *a, **kw: nullcontext())
    monkeypatch.setattr(st, "markdown", lambda *a, **kw: None)
    with pytest.raises(KeyboardInterrupt):
        ChatInterface._render_input_box()
    assert [m["content"] for m in state[manager.KEY_CHAT_MESSAGES]] == ["before", "answer"]
    assert contents(state[manager.KEY_MEMORY]) == ["before", "answer"]
