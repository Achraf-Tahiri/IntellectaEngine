"""Bounded model history owned by one application session.

There is deliberately no process-wide registry. The UI owns the transcript and
rebuilds this window after committing or undoing a complete turn. Routers and
tools receive snapshots and never persist intermediate observations.
"""

from __future__ import annotations

from copy import deepcopy
from collections.abc import Sequence

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage


class MemoryStore:
    """Retain at most ``window_k`` complete user/assistant pairs (default 10)."""

    def __init__(self, window_k: int = 10) -> None:
        if isinstance(window_k, bool) or not isinstance(window_k, int) or window_k < 0:
            raise ValueError("window_k must be a non-negative integer")
        self._window_k = window_k
        self._messages: list[BaseMessage] = []

    @property
    def window_k(self) -> int:
        return self._window_k

    def replace_from_transcript(self, messages: Sequence[dict]) -> None:
        """Replace the window from a transcript of complete, alternating pairs.

        Only the tail is copied. Undo can restore an older turn from the visible
        transcript without retaining an unbounded hidden model-history buffer.
        """
        if len(messages) % 2:
            raise ValueError("Conversation must contain complete turns")
        tail = messages[-2 * self.window_k:] if self.window_k else []
        history: list[BaseMessage] = []
        for i in range(0, len(tail), 2):
            user, assistant = tail[i:i + 2]
            if user["role"] != "user" or assistant["role"] != "assistant":
                raise ValueError("Conversation must alternate user and assistant")
            history.extend([
                HumanMessage(content=user["content"]),
                AIMessage(content=assistant["content"]),
            ])
        self._messages = history

    def get_history(self) -> list[BaseMessage]:
        """Return a detached snapshot, including detached message objects."""
        return deepcopy(self._messages)

    def get_formatted_history(self) -> str:
        """Return the bounded history for a text ReAct prompt."""
        return "\n".join(
            f"{'Human' if message.type == 'human' else 'AI'}: {message.content}"
            for message in self._messages
        )

    def clear(self) -> None:
        """Erase this store, including for callers still holding a reference."""
        self._messages.clear()
