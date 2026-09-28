"""Stateless synchronous ReAct routing with local prompts and fail-fast tools."""

from __future__ import annotations

from langchain_classic.agents import create_react_agent
from langchain_core.tools import StructuredTool

from intellectaengine.core.contracts import (
    AgentContext,
    AgentResult,
    ApplicationError,
    ErrorCode,
    SourceReference,
    require_answer,
    require_query,
)
from intellectaengine.core.execution import BoundedAgentExecutor
from intellectaengine.core.llm_factory import LLMFactory
from intellectaengine.core.prompts import router_prompt
from intellectaengine.tools.chat_tool import ChatTool
from intellectaengine.tools.rag_tool import RAGTool
from intellectaengine.tools.sql_tool import SQLTool
from intellectaengine.tools.web_research_tool import WebResearchTool


class RouterAgent:
    """Use available tools without committing observations or retrying failures."""

    @classmethod
    def run(
        cls,
        query: str,
        provider: str,
        model: str | None = None,
        context: AgentContext | None = None,
        temperature: float = 0.2,
        verbose: bool = False,
        llm_factory=None,
    ) -> AgentResult:
        """Run a bounded local ReAct loop. ``verbose`` is retained but never enabled."""
        ctx = context or AgentContext()
        tool_used = "unknown"
        evidence: list[SourceReference] = []
        stage = ErrorCode.INVALID_CONFIGURATION
        try:
            require_query(query)
            stage = ErrorCode.PROVIDER_FAILURE
            llm = (llm_factory or LLMFactory.create)(
                provider=provider,
                model=model,
                temperature=temperature,
                streaming=False,
            )
            stage = ErrorCode.EXECUTION_FAILURE
            tools = cls._build_tools(llm=llm, context=ctx, evidence_collector=evidence)
            if not tools:
                return AgentResult(
                    answer=ChatTool.run(query, llm, ctx.memory.get_history()),
                    tool_used="chat_direct",
                )
            # Guard each adapter, including schema validation. No tool failure is
            # supplied to the model as a successful observation or retried silently.
            guarded = []
            for tool in tools:

                def invoke(query: str, selected=tool) -> str:
                    nonlocal tool_used
                    tool_used = selected.name
                    try:
                        return require_answer(selected.invoke(query))
                    except ApplicationError:
                        raise
                    except Exception:
                        raise ApplicationError(ErrorCode.TOOL_FAILURE) from None

                guarded.append(
                    StructuredTool.from_function(
                        func=invoke,
                        name=tool.name,
                        description=tool.description,
                        args_schema=tool.args_schema,
                    )
                )
            agent = create_react_agent(llm=llm, tools=guarded, prompt=router_prompt())
            executor = BoundedAgentExecutor(
                agent=agent,
                tools=guarded,
                verbose=False,
                handle_parsing_errors=False,
                max_iterations=6,
                max_execution_time=60,
            )
            raw = executor.invoke(
                {"input": query, "chat_history": ctx.memory.get_formatted_history()}
            )
            return AgentResult(
                require_answer(raw.get("output")),
                "chat_direct" if tool_used == "unknown" else tool_used,
                sources=tuple(dict.fromkeys(evidence)),
            )
        except ApplicationError as exc:
            return AgentResult.failure(exc.code, tool_used)
        except NotImplementedError:
            return AgentResult.failure(ErrorCode.UNSUPPORTED_CAPABILITY, tool_used)
        except Exception:
            return AgentResult.failure(stage, tool_used)

    @staticmethod
    def _build_tools(llm, context: AgentContext, evidence_collector=None) -> list[StructuredTool]:
        tools = []
        if context.vector_store is not None:
            tools.append(
                RAGTool.as_structured_tool(
                    vector_store=context.vector_store,
                    llm=llm,
                    pdf_names=context.pdf_names,
                    evidence_collector=evidence_collector,
                )
            )
        if context.db_uri and context.db_uri.strip():
            tools.append(SQLTool.as_structured_tool(db_uri=context.db_uri, llm=llm))
        tools.append(WebResearchTool.as_structured_tool())
        tools.append(ChatTool.as_structured_tool(llm=llm, history=context.memory.get_history()))
        return tools
