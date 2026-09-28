"""Shared synchronous outcomes; failure text never includes exception payloads."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from intellectaengine.core.memory_store import MemoryStore


class ErrorCode(StrEnum):
    INVALID_CONFIGURATION = "invalid_configuration"
    MISSING_RESOURCE = "missing_resource"
    UNSUPPORTED_CAPABILITY = "unsupported_capability"
    PROVIDER_FAILURE = "provider_failure"
    TOOL_FAILURE = "tool_failure"
    EXECUTION_FAILURE = "execution_failure"
    EXECUTION_LIMIT = "execution_limit"
    INGESTION_FAILURE = "ingestion_failure"
    INDEX_FAILURE = "index_failure"
    RESOURCE_LIMIT = "resource_limit"


# Allowlisted messages/diagnostics, not regex filtering of arbitrary secrets.
_MESSAGES = {
    ErrorCode.INVALID_CONFIGURATION: "Check the selected mode, provider, model, and required credentials.",
    ErrorCode.MISSING_RESOURCE: "Load the required PDFs or connect a database before using this mode.",
    ErrorCode.UNSUPPORTED_CAPABILITY: "The selected model does not support the capability required by this mode.",
    ErrorCode.PROVIDER_FAILURE: "The model provider could not complete the request. Check its configuration and availability.",
    ErrorCode.TOOL_FAILURE: "The selected tool could not complete the request. Check its resources and availability.",
    ErrorCode.EXECUTION_FAILURE: "The agent could not complete the request. Try rephrasing it or selecting a forced mode.",
    ErrorCode.EXECUTION_LIMIT: "The agent reached its execution limit. Try a simpler question or a forced mode.",
    ErrorCode.INGESTION_FAILURE: "The uploaded PDFs could not be processed safely. Review the ingestion report and try another batch.",
    ErrorCode.INDEX_FAILURE: "The document index operation could not be verified. Check storage availability before retrying.",
    ErrorCode.RESOURCE_LIMIT: "The document operation exceeded a configured safety limit.",
}


class ApplicationError(Exception):
    """Typed failures propagate through tools without becoming observations."""

    def __init__(self, code: ErrorCode):
        self.code = code
        super().__init__(_MESSAGES[code])


@dataclass
class AgentContext:
    """Caller-owned resources. Consumers may read history but never persist it."""

    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    memory: MemoryStore = field(default_factory=MemoryStore)
    vector_store: Any = None
    db_uri: str | None = None
    pdf_names: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SourceReference:
    """A retrieved document reference, not a claim-level verification."""

    source: str | None
    page: int | None


@dataclass(frozen=True)
class AgentResult:
    answer: str
    tool_used: str = "unknown"
    error: ErrorCode | None = None
    sources: tuple[SourceReference, ...] = ()

    @property
    def ok(self) -> bool:
        return self.error is None

    @classmethod
    def failure(cls, code: ErrorCode, tool_used: str = "unknown") -> AgentResult:
        # Only enum values and registered tool names belong in diagnostics.
        logging.getLogger(__name__).warning("Request failed: code=%s", code.value)
        return cls(answer=f"⚠️ {_MESSAGES[code]}", tool_used=tool_used, error=code)


def require_query(query: str) -> None:
    if not isinstance(query, str) or not query.strip():
        raise ApplicationError(ErrorCode.INVALID_CONFIGURATION)


def require_answer(answer: Any) -> str:
    if not isinstance(answer, str) or not answer.strip():
        raise ApplicationError(ErrorCode.EXECUTION_FAILURE)
    return answer
