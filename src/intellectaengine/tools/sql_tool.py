"""Natural-language SQL through the shared, bounded SQLite-only policy."""

from langchain_community.agent_toolkits import create_sql_agent
from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from intellectaengine.core.contracts import ApplicationError, ErrorCode, require_query, require_answer
from intellectaengine.core.execution import BoundedAgentExecutor
from intellectaengine.core.sql_policy import PolicySQLDatabase, SQLitePolicy, bounded_text


class SQLToolInput(BaseModel):
    query: str = Field(
        description="A natural language question about the connected SQLite database."
    )


class BoundedSQLToolkit(SQLDatabaseToolkit):
    def get_tools(self):
        result = []
        for tool in super().get_tools():

            def invoke(_tool=tool, **kwargs):
                try:
                    return bounded_text(
                        str(_tool.invoke(kwargs)), self.db.policy.config.sql_observation_char_limit
                    )
                except ApplicationError:
                    raise
                except Exception:
                    raise ApplicationError(ErrorCode.TOOL_FAILURE) from None

            description = tool.description
            if tool.name == "sql_db_schema":
                description = "Get schema definitions for comma-separated table names. No sample data is included."
            elif tool.name == "sql_db_query":
                description = "Execute one read-only SQLite query. Results are bounded and truncation is marked. Errors terminate the request."
            result.append(
                StructuredTool.from_function(
                    func=invoke,
                    name=tool.name,
                    description=description,
                    args_schema=tool.args_schema,
                )
            )
        return result


class SQLTool:
    @classmethod
    def run(cls, query, db_uri, llm, top_k=None):
        require_query(query)
        cls.require_resource(db_uri)
        try:
            policy = SQLitePolicy(top_k=top_k)
            db = cls._connect(db_uri)
            db.policy = policy
            agent = cls._build_agent(db=db, llm=llm, top_k=policy.row_limit)
            answer = require_answer(agent.invoke({"input": query}).get("output"))
            # In automatic mode this reply becomes an outer router observation.
            return bounded_text(answer, policy.config.sql_observation_char_limit)
        except ApplicationError:
            raise
        except Exception:
            raise ApplicationError(ErrorCode.TOOL_FAILURE) from None

    @staticmethod
    def require_resource(db_uri):
        with SQLitePolicy().resolve(db_uri):
            pass

    @staticmethod
    def get_table_names(db_uri):
        return sorted(SQLitePolicy().schema(db_uri))

    @classmethod
    def as_structured_tool(cls, db_uri, llm, top_k=None):
        def run(query: str):
            return cls.run(query=query, db_uri=db_uri, llm=llm, top_k=top_k)

        return StructuredTool.from_function(
            func=run,
            name="sql_database_query",
            description="Query the connected SQLite database using natural language for data or analytics questions. Input the user's exact question.",
            args_schema=SQLToolInput,
        )

    @staticmethod
    def _connect(db_uri):
        return PolicySQLDatabase(db_uri)

    @staticmethod
    def _build_agent(db, llm, top_k):
        if not callable(getattr(llm, "bind_tools", None)):
            raise ApplicationError(ErrorCode.UNSUPPORTED_CAPABILITY)
        try:
            executor = create_sql_agent(
                llm=llm,
                toolkit=BoundedSQLToolkit(db=db, llm=llm),
                top_k=top_k,
                verbose=False,
                agent_type="tool-calling",
                max_iterations=6,
                max_execution_time=60,
            )
        except NotImplementedError:
            raise ApplicationError(ErrorCode.UNSUPPORTED_CAPABILITY) from None
        return BoundedAgentExecutor(
            agent=executor.agent,
            tools=executor.tools,
            verbose=False,
            handle_parsing_errors=False,
            max_iterations=6,
            max_execution_time=60,
        )
