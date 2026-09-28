"""SQLite policy and LangChain database adapter; no pooled engines or live handles.

Only the operator controls approved roots. SQL text is untrusted. Native SQLite
permissions, not the model/checker, authorize statements. This is not a sandbox
against local processes, malicious database files, or filesystem replacement races.
"""

from contextlib import ExitStack, contextmanager
from importlib.resources import as_file, files
from pathlib import Path
import sqlite3
import time

from langchain_community.utilities.sql_database import SQLDatabase
from sqlalchemy.engine import make_url

from intellectaengine.config.settings import settings
from intellectaengine.core.contracts import ApplicationError, ErrorCode

SAMPLE_DB = "USE_SAMPLE_DB"
CHINOOK_DB_RESOURCE = files("intellectaengine").joinpath("assets", "Chinook.db")
TRUNCATED = "\n[truncated]"
# A deliberately finite set: no extension/file functions, virtual-table PRAGMAs,
# or user-defined functions. Additional functions need review and boundary tests.
READ_FUNCTIONS = frozenset(
    """
abs avg count sum total min max round coalesce ifnull nullif iif
lower upper length octet_length substr substring trim ltrim rtrim replace instr
like glob unicode char hex unhex quote typeof concat concat_ws format printf
random randomblob zeroblob sign mod ceil ceiling floor sqrt pow power exp ln log log10 log2
acos acosh asin asinh atan atan2 atanh cos cosh sin sinh tan tanh degrees radians pi trunc
 date time datetime julianday unixepoch strftime timediff
 group_concat string_agg row_number rank dense_rank percent_rank cume_dist ntile
lag lead first_value last_value nth_value
json json_array json_object json_extract json_type json_valid json_quote
json_array_length json_group_array json_group_object json_patch json_remove
json_replace json_set json_insert json_error_position
sqlite_version sqlite_source_id
""".split()
)


def bounded_text(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - len(TRUNCATED)] + TRUNCATED


class SQLitePolicy:
    def __init__(self, config=None, top_k=None):
        self.config = config or settings
        self.row_limit = self.config.sql_top_k if top_k is None else top_k
        if type(self.row_limit) is not int or not 1 <= self.row_limit <= self.config.sql_top_k:
            raise ApplicationError(ErrorCode.INVALID_CONFIGURATION)

    @contextmanager
    def resolve(self, uri: str | None):
        """Keep extracted package data alive for the entire consuming operation."""
        with ExitStack() as resources:
            if not isinstance(uri, str) or not uri.strip():
                raise ApplicationError(ErrorCode.MISSING_RESOURCE)
            try:
                if uri.strip() == SAMPLE_DB:
                    path = resources.enter_context(as_file(CHINOOK_DB_RESOURCE)).resolve(strict=True)
                else:
                    url = make_url(uri)
                    if (
                        url.drivername not in {"sqlite", "sqlite+pysqlite"}
                        or url.username is not None
                        or url.password is not None
                        or url.host is not None
                        or url.port is not None
                        or url.query
                        or not url.database
                        or url.database == ":memory:"
                        or url.database.startswith("file:")
                        or "?" in uri
                        or "#" in uri
                    ):
                        raise ApplicationError(ErrorCode.INVALID_CONFIGURATION)
                    # Absolute custom paths avoid process-cwd dependent approval.
                    candidate = Path(url.database)
                    if not candidate.is_absolute():
                        raise ApplicationError(ErrorCode.INVALID_CONFIGURATION)
                    path = candidate.resolve(strict=True)
                    roots = [Path(root).resolve(strict=True) for root in self.config.sql_allowed_roots]
                    if not any(root.is_dir() and path.is_relative_to(root) for root in roots):
                        raise ApplicationError(ErrorCode.INVALID_CONFIGURATION)
                if not path.is_file():
                    raise ApplicationError(ErrorCode.MISSING_RESOURCE)

            except ApplicationError:
                raise
            except FileNotFoundError:
                raise ApplicationError(ErrorCode.MISSING_RESOURCE) from None
            except Exception:
                raise ApplicationError(ErrorCode.INVALID_CONFIGURATION) from None
            yield path

    @staticmethod
    def authorize(action, arg1, arg2, database, source):
        if action in {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_RECURSIVE}:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_READ:
            # SQLite's count(*) fast path reports an empty column and no
            # database name. ATTACH and temporary objects remain forbidden.
            main_read = database == "main" or (database is None and arg2 == "")
            if main_read and not (arg1 or "").lower().startswith("pragma_"):
                return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_FUNCTION and (arg2 or "").lower() in READ_FUNCTIONS:
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY

    @contextmanager
    def connection(self, uri):
        with self.resolve(uri) as path:  # Revalidate and retain the resource until close.
            conn = None
            interrupted = False
            try:
                conn = sqlite3.connect(
                    path.as_uri() + "?mode=ro",
                    uri=True,
                    timeout=self.config.sql_lock_timeout_ms / 1000,
                    cached_statements=0,
                )
                conn.enable_load_extension(False)
                conn.execute("PRAGMA query_only=ON").close()
                conn.execute("PRAGMA trusted_schema=OFF").close()
                conn.execute("PRAGMA temp_store=MEMORY").close()
                # Defense in depth for large SQLite allocations; output limits below
                # are separate. Oversize values fail safely instead of being fetched.
                conn.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 1_000_000)
                conn.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, 100_000)
                conn.setlimit(sqlite3.SQLITE_LIMIT_ATTACHED, 0)
                conn.set_authorizer(self.authorize)
                deadline = time.monotonic() + self.config.sql_statement_seconds
                steps = 0

                def progress():
                    nonlocal steps, interrupted
                    steps += 1000
                    interrupted = (
                        steps >= self.config.sql_statement_steps or time.monotonic() >= deadline
                    )
                    return int(interrupted)

                conn.set_progress_handler(progress, 1000)
                yield conn
            except ApplicationError:
                raise
            except Exception:
                code = ErrorCode.EXECUTION_LIMIT if interrupted else ErrorCode.TOOL_FAILURE
                raise ApplicationError(code) from None
            finally:
                if conn is not None:
                    conn.close()

    def query(self, uri, command):
        if not isinstance(command, str):
            raise ApplicationError(ErrorCode.INVALID_CONFIGURATION)
        with self.connection(uri) as conn:
            # sqlite3.execute rejects multiple statements at the real boundary.
            cursor = conn.execute(command)
            try:
                if cursor.description is None:
                    raise ApplicationError(ErrorCode.TOOL_FAILURE)
                parts = []
                used = 0
                for _ in range(self.row_limit):
                    row = cursor.fetchone()
                    if row is None:
                        break
                    cells = [
                        bounded_text(repr(cell), self.config.sql_cell_char_limit) for cell in row
                    ]
                    line = "(" + ", ".join(cells) + ")\n"
                    remaining = self.config.sql_observation_char_limit - used
                    if len(line) > remaining - len(TRUNCATED):
                        parts.append(bounded_text(line, remaining))
                        # If it happened to fit but reserved marker space did not,
                        # still signal that later rows were not consumed.
                        return bounded_text(
                            "".join(parts) + TRUNCATED, self.config.sql_observation_char_limit
                        )
                    parts.append(line)
                    used += len(line)
                else:
                    if cursor.fetchone() is not None:  # One overflow sentinel only.
                        parts.append(TRUNCATED)
                return "".join(parts) or "[]"
            finally:
                cursor.close()

    def schema(self, uri):
        """Trusted fixed introspection; no model SQL and no sample data rows.

        Read sqlite_schema directly, avoiding general SQLAlchemy PRAGMA privileges.
        Fail on an oversized inventory rather than claiming a partial validation.
        """
        with self.connection(uri) as conn:
            cursor = conn.execute(
                "SELECT name, sql FROM sqlite_schema "
                "WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
            try:
                schema = {}
                size = 0
                for name, definition in cursor:
                    size += len(name) + len(definition or "") + 4
                    if size > self.config.sql_observation_char_limit:
                        raise ApplicationError(ErrorCode.EXECUTION_LIMIT)
                    schema[name] = definition or ""
                return schema
            finally:
                cursor.close()


class PolicySQLDatabase(SQLDatabase):
    """Implement only the toolkit's public surface, without an SQLAlchemy engine.

    Inherited engine execution cannot provide an alternate connection. All query
    entry points used by the locked toolkit route through SQLitePolicy.query.
    """

    def __init__(self, uri, policy=None):
        self.policy = policy or SQLitePolicy()
        self.uri = uri
        self._schema = self.policy.schema(uri)

    @property
    def dialect(self):
        return "sqlite"

    def get_usable_table_names(self):
        return sorted(self._schema)

    def get_table_info(self, table_names=None, **kwargs):
        names = self.get_usable_table_names() if table_names is None else table_names
        if any(name not in self._schema for name in names):
            raise ApplicationError(ErrorCode.TOOL_FAILURE)
        return bounded_text(
            ";\n".join(self._schema[name] for name in names),
            self.policy.config.sql_observation_char_limit,
        )

    def get_table_info_no_throw(self, table_names=None):
        return self.get_table_info(table_names)

    def run(self, command, fetch="all", **kwargs):
        if fetch != "all" or kwargs:
            raise ApplicationError(ErrorCode.INVALID_CONFIGURATION)
        return self.policy.query(self.uri, command)

    def run_no_throw(self, command, **kwargs):
        return self.run(command, **kwargs)
