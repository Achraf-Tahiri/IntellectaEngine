"""Headless application boundary. Callers alone commit final conversation turns."""

from intellectaengine.core.contracts import (
    AgentContext,
    AgentResult,
    ApplicationError,
    ErrorCode,
    require_answer,
    require_query,
)
from intellectaengine.core.llm_factory import LLMFactory
from intellectaengine.core.router_agent import RouterAgent
from intellectaengine.tools.chat_tool import ChatTool
from intellectaengine.tools.rag_tool import RAGTool
from intellectaengine.tools.sql_tool import SQLTool
from intellectaengine.tools.web_research_tool import WebResearchTool


class ApplicationService:
    """Dispatch one request; the caller owns rendering and history persistence."""

    @staticmethod
    def run(
        query: str,
        provider: str,
        model: str | None = None,
        context: AgentContext | None = None,
        mode: str = "auto",
        llm_factory=None,
    ) -> AgentResult:
        """Return a final success/failure; interruptions propagate without a result."""
        context = context or AgentContext()
        names = {
            "rag": "rag_document_search",
            "sql": "sql_database_query",
            "web": "web_research",
            "chat": "general_chat",
        }
        tool = names.get(mode, "unknown")
        stage = ErrorCode.INVALID_CONFIGURATION
        try:
            require_query(query)
            if mode not in {"auto", *names}:
                raise ApplicationError(ErrorCode.INVALID_CONFIGURATION)
            if mode == "auto":
                return RouterAgent.run(query, provider, model, context, llm_factory=llm_factory)
            if mode == "rag" and context.vector_store is None:
                raise ApplicationError(ErrorCode.MISSING_RESOURCE)
            if mode == "sql":
                SQLTool.require_resource(context.db_uri)
            if mode == "web":
                stage = ErrorCode.TOOL_FAILURE
                return AgentResult(require_answer(WebResearchTool.run(query=query)), tool)
            stage = ErrorCode.PROVIDER_FAILURE
            llm = (llm_factory or LLMFactory.create)(
                provider=provider, model=model, streaming=False
            )
            stage = ErrorCode.TOOL_FAILURE
            sources = ()
            if mode == "rag":
                rag_result = RAGTool.run(
                    query=query,
                    vector_store=context.vector_store,
                    llm=llm,
                    pdf_names=context.pdf_names,
                    return_result=True,
                )
                answer = rag_result.answer
                sources = rag_result.sources
            elif mode == "sql":
                answer = SQLTool.run(query=query, db_uri=context.db_uri, llm=llm)
            else:
                answer = ChatTool.run(query=query, llm=llm, history=context.memory.get_history())
            return AgentResult(
                require_answer(answer), tool, sources=sources if mode == "rag" else ()
            )
        except ApplicationError as exc:
            return AgentResult.failure(exc.code, tool)
        except Exception:
            return AgentResult.failure(stage, tool)
