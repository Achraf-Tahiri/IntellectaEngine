"""LangChain adapter exposing exhaustion as a typed failure, not success text."""

from langchain_classic.agents import AgentExecutor

from intellectaengine.core.contracts import ApplicationError, ErrorCode


class BoundedAgentExecutor(AgentExecutor):
    def _perform_agent_action(
        self, name_to_tool_map, color_mapping, agent_action, run_manager=None
    ):
        if agent_action.tool not in name_to_tool_map:
            raise ApplicationError(ErrorCode.TOOL_FAILURE)
        return super()._perform_agent_action(
            name_to_tool_map,
            color_mapping,
            agent_action,
            run_manager,
        )

    def _should_continue(self, iterations: int, time_elapsed: float) -> bool:
        if not super()._should_continue(iterations, time_elapsed):
            raise ApplicationError(ErrorCode.EXECUTION_LIMIT)
        return True
