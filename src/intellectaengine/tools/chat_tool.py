"""
tools/chat_tool.py
===================
General Conversational Chat Tool.

This tool handles free-form conversational queries that do not require
document retrieval, database access, or web search. It acts as the
intelligent fallback in the router agent's tool chain, providing context-
aware responses by injecting the session's bounded conversation history into
the prompt.

Key features:
- Retrieves and injects conversation history from ``MemoryStore``
- Does not persist tool observations; the UI commits the final reply
- Well-crafted system prompt that defines the assistant's persona
- Uses the selected LLM provider for inference
- StructuredTool registration for router agent compatibility

Usage (standalone):
    from intellectaengine.tools.chat_tool import ChatTool

    response = ChatTool.run(
        query="Can you explain the difference between RAG and fine-tuning?",
        llm=my_llm,
        history=memory.get_history(),
    )

Usage (as agent tool):
    tool = ChatTool.as_structured_tool(llm=my_llm, history=memory.get_history())
"""

from __future__ import annotations

import logging

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field


from intellectaengine.core.contracts import ApplicationError, ErrorCode, require_query, require_answer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System persona for the conversational tool
# ---------------------------------------------------------------------------

_CHAT_SYSTEM_PROMPT = """You are IntellectaEngine, a world-class AI assistant \
specialised in Data Science, Machine Learning, Knowledge Engineering, \
and Software Architecture.

Your responses should be:
- **Accurate**: Grounded in established knowledge. Acknowledge uncertainty clearly.
- **Structured**: Use markdown headers, bullet lists, and code blocks for clarity.
- **Concise but complete**: Never pad responses; never truncate important information.
- **Contextually aware**: Reference earlier parts of the conversation when relevant.

You have access to specialised tools for:
- Searching uploaded PDF documents (RAG)
- Querying SQL databases
- Browsing the internet for current information

When you use only your internal knowledge, state this clearly."""


# ---------------------------------------------------------------------------
# Pydantic input schema
# ---------------------------------------------------------------------------

class ChatToolInput(BaseModel):
    """Input schema for the chat structured tool."""

    query: str = Field(
        description=(
            "A general conversational question or request. "
            "Use this tool for knowledge questions, explanations, code help, "
            "creative writing, or any topic not requiring documents, databases, "
            "or live internet search."
        )
    )


class ChatTool:
    """
    Stateless general-purpose conversational tool backed by the session memory.

    This tool is always registered as the last tool in the router agent's
    list, ensuring there is always a fallback for queries that don't
    require specialised retrieval.

    The tool builds a message list consisting of:
        1. A ``SystemMessage`` defining the assistant persona
        2. Recent ``BaseMessage`` objects from ``MemoryStore``
        3. The current ``HumanMessage``

    This gives the LLM bounded conversational context on every call.
    """

    @classmethod
    def run(
        cls,
        query: str,
        llm: BaseChatModel,
        history: list[BaseMessage] | None = None,
    ) -> str:
        """
        Execute a conversational query using the provided LLM and session memory.

        Args:
            query:      The user's conversational question or statement.
            llm:        Instantiated ``BaseChatModel`` for inference.
            history:    Detached bounded conversation history; empty by default.

        Returns:
            The LLM's response as a plain string. Raises ApplicationError if inference fails.

        Raises:
            ApplicationError: A safe, typed failure.

        Example:
            >>> ChatTool.run("What is the difference between LSTM and Transformer?", llm)
            'LSTMs process sequences step-by-step...'
        """
        require_query(query)

        try:
            messages: list[BaseMessage] = cls._build_messages(query, history or [])

            response = llm.invoke(messages)
            answer: str = (
                response.content
                if hasattr(response, "content")
                else str(response)
            )

            return require_answer(answer)

        except ApplicationError:
            raise
        except Exception:
            raise ApplicationError(ErrorCode.PROVIDER_FAILURE) from None

    @classmethod
    def as_structured_tool(
        cls,
        llm: BaseChatModel,
        history: list[BaseMessage] | None = None,
    ) -> StructuredTool:
        """
        Wrap ``ChatTool.run`` as a LangChain ``StructuredTool`` for use within
        the router agent's tool registry.

        Args:
            llm:        Instantiated LLM for inference.
            history:    Detached bounded conversation history.

        Returns:
            A ``StructuredTool`` registered under the name
            ``'general_chat'``.

        Example:
            >>> tool = ChatTool.as_structured_tool(llm, history=[])
            >>> tool.name
            'general_chat'
        """
        def _run(query: str) -> str:
            return cls.run(query=query, llm=llm, history=history)

        return StructuredTool.from_function(
            func=_run,
            name="general_chat",
            description=(
                "Answer general knowledge questions, explain concepts, help with code, "
                "or carry on a conversation. "
                "Use this tool when the query does NOT require searching documents, "
                "querying a database, or browsing the internet. "
                "This is the default fallback for conversational, explanatory, "
                "or creative queries. Input should be the user's exact question."
            ),
            args_schema=ChatToolInput,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_messages(
        query: str,
        history: list[BaseMessage],
    ) -> list[BaseMessage]:
        """
        Construct the full message list for the LLM call.

        The message structure is:
            [SystemMessage(persona), *history, HumanMessage(query)]

        Args:
            query:   The current user message text.
            history: Prior conversation messages from ``MemoryStore``.

        Returns:
            Ordered list of ``BaseMessage`` objects ready for LLM invocation.
        """
        messages: list[BaseMessage] = [SystemMessage(content=_CHAT_SYSTEM_PROMPT)]
        messages.extend(history)
        messages.append(HumanMessage(content=query))
        return messages
