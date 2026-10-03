"""Safety probes use disposable databases and the native sqlite3 boundary."""

import sqlite3

import pytest


@pytest.fixture
def database(tmp_path):
    root = tmp_path / "approved"
    root.mkdir()
    path = root / "data.db"
    with sqlite3.connect(path) as conn:
        conn.executescript(
            "CREATE TABLE artists(id INTEGER PRIMARY KEY, name TEXT);"
            "CREATE TABLE albums(artist INTEGER, title TEXT);"
            "INSERT INTO artists VALUES (1, 'Ada'), (2, 'Lin');"
            "INSERT INTO albums VALUES (1, 'First'), (1, 'Second'), (2, 'Third');"
        )
    return root, path, "sqlite:///" + str(path)


def policy(root, **kwargs):
    from intellectaengine.config.settings import AppSettings
    from intellectaengine.core.sql_policy import SQLitePolicy

    return SQLitePolicy(AppSettings(_env_file=None, sql_allowed_roots=[str(root)], **kwargs))


def test_sample_and_approved_reads(database):
    from intellectaengine.core.sql_policy import SQLitePolicy

    root, _, uri = database
    assert "275" in SQLitePolicy().query("USE_SAMPLE_DB", "SELECT count(*) FROM Artist")
    assert "Ada" in policy(root).query(uri, "SELECT name FROM artists")


@pytest.mark.parametrize(
    "uri",
    [
        "postgresql://user:SYNTHETIC-SECRET@host/db",
        "mysql://host/db",
        "sqlite:///:memory:",
        "sqlite://",
        "sqlite:///relative.db",
        "sqlite:////tmp/data.db?mode=rw",
        "sqlite:////tmp/data.db?",
        "sqlite:///file:/tmp/data.db",
        "sqlite://user:secret@host/tmp/data.db",
    ],
)
def test_invalid_inputs_rejected_before_open(monkeypatch, uri):
    from intellectaengine.core.contracts import ApplicationError
    from intellectaengine.core.sql_policy import SQLitePolicy

    def forbidden(*args, **kwargs):
        pytest.fail("Rejected URI opened a connection")

    monkeypatch.setattr(sqlite3, "connect", forbidden)
    with pytest.raises(ApplicationError):
        SQLitePolicy().query(uri, "SELECT 1")


def test_missing_disabled_custom_and_path_confinement(database, tmp_path, monkeypatch):
    from intellectaengine.core.contracts import ApplicationError
    from intellectaengine.core.sql_policy import SQLitePolicy

    root, path, uri = database
    sibling = tmp_path / "approved-escape"
    sibling.mkdir()
    outside = sibling / "data.db"
    outside.write_bytes(path.read_bytes())
    (root / "escape.db").symlink_to(outside)
    (root / "inside.db").symlink_to(path)
    approved = policy(root)
    assert "Ada" in approved.query(
        "sqlite:///" + str(root / "inside.db"), "SELECT name FROM artists"
    )

    def forbidden(*args, **kwargs):
        pytest.fail("Disallowed path opened a connection")

    monkeypatch.setattr(sqlite3, "connect", forbidden)
    for rejected in [
        outside,
        root / "escape.db",
        root / ".." / "approved-escape" / "data.db",
        root / "missing.db",
    ]:
        with pytest.raises(ApplicationError):
            approved.query("sqlite:///" + str(rejected), "SELECT 1")
    with pytest.raises(ApplicationError):
        SQLitePolicy().query(uri, "SELECT 1")
    assert not (root / "missing.db").exists()


DENIED = [
    "INSERT INTO artists VALUES (3, 'bad')",
    "UPDATE artists SET name='bad'",
    "DELETE FROM artists",
    "CREATE TABLE bad(id)",
    "DROP TABLE albums",
    "ALTER TABLE artists ADD COLUMN bad",
    "CREATE TEMP TABLE bad(id)",
    "ATTACH DATABASE ':memory:' AS other",
    "DETACH DATABASE main",
    "VACUUM INTO 'escaped.db'",
    "PRAGMA query_only=OFF",
    "PRAGMA trusted_schema=ON",
    "PRAGMA writable_schema=ON",
    "PRAGMA busy_timeout=999999",
    "PRAGMA table_info(artists)",
    "SELECT * FROM pragma_table_info('artists')",
    "SELECT load_extension('SYNTHETIC-SECRET')",
    "SELECT writefile('escaped.db', 'bad')",
    "SELECT 1; SELECT 2",
    "WITH v AS (SELECT 1) DELETE FROM artists",
    "BEGIN",
]


@pytest.mark.parametrize("statement", DENIED)
def test_native_authorization_denies_unsafe_sql(database, statement, tmp_path):
    from intellectaengine.core.contracts import ApplicationError

    root, path, uri = database
    before = path.read_bytes()
    with pytest.raises(ApplicationError):
        policy(root).query(uri, statement)
    assert path.read_bytes() == before
    assert not (tmp_path / "escaped.db").exists()
    assert "Ada" in policy(root).query(uri, "SELECT name FROM artists")


@pytest.mark.parametrize(
    "statement,expected",
    [
        (
            "SELECT name, count(*) FROM artists JOIN albums ON artists.id=albums.artist GROUP BY name",
            "('Ada', 2)",
        ),
        (
            "WITH counts AS (SELECT artist, count(*) AS n FROM albums GROUP BY artist) SELECT sum(n) FROM counts",
            "(3,)",
        ),
        (
            "WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n WHERE x<5) SELECT sum(x) FROM n",
            "(15,)",
        ),
        ("SELECT 'SELECT; DELETE'", "SELECT; DELETE"),
    ],
)
def test_analytical_reads(database, statement, expected):
    root, _, uri = database
    # Output is formatted as rows, without a trailing comma for single cells.
    assert expected.replace(",)", ")") in policy(root).query(uri, statement)


def test_bounded_fetch_cells_observations_and_explicit_truncation(database):
    root, _, uri = database
    p = policy(root, sql_top_k=2, sql_cell_char_limit=64, sql_observation_char_limit=128)
    output = p.query(uri, "SELECT title FROM albums")
    assert "First" in output and "Second" in output and "Third" not in output
    assert "[truncated]" in output
    output = p.query(uri, "SELECT printf('%10000s', 'SYNTHETIC-TAIL'), hex(zeroblob(10000))")
    assert len(output) <= 128 and "[truncated]" in output and "SYNTHETIC-TAIL" not in output
    # The VM would exceed its work budget if the implementation fetched all rows.
    output = p.query(
        uri,
        "WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n WHERE x<100000000) SELECT x FROM n",
    )
    assert "[truncated]" in output


def test_oversize_sqlite_value_fails_safely(database):
    from intellectaengine.core.contracts import ApplicationError

    root, _, uri = database
    with pytest.raises(ApplicationError):
        policy(root).query(uri, "SELECT zeroblob(2000000)")


@pytest.fixture
def tracked_connections(monkeypatch):
    opened = []
    original = sqlite3.connect

    class Tracked(sqlite3.Connection):
        closed = False

        def close(self):
            self.closed = True
            return super().close()

    def connect(*args, **kwargs):
        conn = original(*args, **kwargs, factory=Tracked)
        opened.append(conn)
        return conn

    monkeypatch.setattr(sqlite3, "connect", connect)
    return opened


@pytest.mark.parametrize("budget", ["work", "deadline"])
def test_expensive_query_interrupts_and_closes(database, tracked_connections, budget):
    from intellectaengine.core.contracts import ApplicationError, ErrorCode

    root, _, uri = database
    limits = (
        {"sql_statement_steps": 1000} if budget == "work" else {"sql_statement_seconds": 0.000001}
    )
    p = policy(root, **limits)
    with pytest.raises(ApplicationError) as exc:
        p.query(
            uri,
            "WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n WHERE x<100000000) SELECT sum(x) FROM n",
        )
    assert exc.value.code == ErrorCode.EXECUTION_LIMIT
    assert tracked_connections and all(c.closed for c in tracked_connections)
    # A new operation gets a fresh budget and protections.
    assert "Ada" in p.query(uri, "SELECT name FROM artists")
    with pytest.raises(ApplicationError):
        p.query(uri, "PRAGMA query_only=OFF")
    assert all(c.closed for c in tracked_connections)


def test_lock_wait_is_bounded_and_closes(database, tracked_connections):
    import time

    from intellectaengine.core.contracts import ApplicationError

    root, path, uri = database
    writer = sqlite3.connect(path)
    try:
        writer.execute("BEGIN EXCLUSIVE")
        start = time.monotonic()
        with pytest.raises(ApplicationError):
            policy(root, sql_lock_timeout_ms=20).query(uri, "SELECT * FROM artists")
        assert time.monotonic() - start < 2
        assert all(c.closed for c in tracked_connections if c is not writer)
    finally:
        writer.close()


def test_introspection_failure_not_empty_success(
    database, tracked_connections, monkeypatch, caplog
):
    import intellectaengine.core.sql_policy as module
    from intellectaengine.connectors.database_connector import DatabaseConnector
    from intellectaengine.core.contracts import ApplicationError

    root, path, uri = database
    monkeypatch.setattr(module, "settings", policy(root).config)
    path.write_bytes(b"SYNTHETIC-SECRET corrupt database")
    with pytest.raises(ApplicationError):
        DatabaseConnector.get_table_names(uri)
    ok, message = DatabaseConnector.validate_uri(uri)
    assert not ok
    assert "SYNTHETIC-SECRET" not in message + caplog.text
    assert all(c.closed for c in tracked_connections)


def test_initialization_and_connect_failure_safe_cleanup(
    database, tracked_connections, monkeypatch, caplog
):
    from intellectaengine.core.contracts import ApplicationError

    root, _, uri = database
    p = policy(root)

    def fail(*args, **kwargs):
        raise RuntimeError("SYNTHETIC-SECRET")

    p.query(uri, "SELECT 1")
    # A native connection exists when protection setup fails.
    monkeypatch.setattr(type(tracked_connections[0]), "enable_load_extension", fail)
    with pytest.raises(ApplicationError) as exc:
        p.query(uri, "SELECT 1")
    assert all(c.closed for c in tracked_connections)
    assert "SYNTHETIC-SECRET" not in str(exc.value) + caplog.text
    monkeypatch.setattr(sqlite3, "connect", fail)
    with pytest.raises(ApplicationError) as exc:
        p.query(uri, "SELECT 1")
    assert "SYNTHETIC-SECRET" not in str(exc.value) + caplog.text


def test_real_toolkit_has_no_unrestricted_execution_path(database):
    from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit
    from langchain_core.language_models.fake import FakeListLLM

    from intellectaengine.core.contracts import ApplicationError
    from intellectaengine.core.sql_policy import PolicySQLDatabase

    root, _, uri = database
    db = PolicySQLDatabase(uri, policy(root))
    tools = {
        t.name: t
        for t in SQLDatabaseToolkit(db=db, llm=FakeListLLM(responses=["unused"])).get_tools()
    }
    schema = tools["sql_db_schema"].invoke({"table_names": "artists"})
    assert "CREATE TABLE" in schema and "Ada" not in schema
    for statement in DENIED:
        with pytest.raises(ApplicationError):
            tools["sql_db_query"].invoke({"query": statement})
    assert "Ada" in tools["sql_db_query"].invoke({"query": "SELECT name FROM artists"})
    for method in [db.run, db.run_no_throw]:
        with pytest.raises(ApplicationError):
            method("DROP TABLE artists")
    with pytest.raises(ApplicationError):
        db.run("SELECT 1", fetch="cursor")


@pytest.mark.parametrize("top_k", [0, -1, True, 1.5, 11])
def test_row_override_cannot_disable_or_raise_policy_limit(top_k):
    from intellectaengine.core.contracts import ApplicationError
    from intellectaengine.core.sql_policy import SQLitePolicy

    with pytest.raises(ApplicationError):
        SQLitePolicy(top_k=top_k)


def test_encoded_path_characters_use_literal_file(database):
    root, path, _ = database
    special = root / "a %20 b.db"
    special.write_bytes(path.read_bytes())
    assert "Ada" in policy(root).query("sqlite:///" + str(special), "SELECT name FROM artists")


def test_valid_empty_schema_and_schema_budget(database):
    from intellectaengine.core.contracts import ApplicationError

    root, path, uri = database
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE extra_metadata(a TEXT, b TEXT, c TEXT, d TEXT)")
    with pytest.raises(ApplicationError):
        policy(root, sql_observation_char_limit=128).schema(uri)
    with sqlite3.connect(path) as conn:
        conn.executescript("DROP TABLE artists; DROP TABLE albums; DROP TABLE extra_metadata;")
    assert policy(root).schema(uri) == {}


@pytest.mark.parametrize("failure", ["model", "generation", "execution", "success"])
def test_agent_closes_all_connections_and_hides_secrets(
    database, tracked_connections, monkeypatch, caplog, failure
):
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.messages import AIMessage

    import intellectaengine.core.sql_policy as module
    from intellectaengine.core.application import ApplicationService
    from intellectaengine.core.contracts import AgentContext

    root, _, uri = database
    monkeypatch.setattr(module, "settings", policy(root).config)

    class Model(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            if failure == "model":
                raise RuntimeError("SYNTHETIC-SECRET driver text")
            return self

        def _generate(self, *args, **kwargs):
            if failure == "generation":
                raise RuntimeError("SYNTHETIC-SECRET model response")
            return super()._generate(*args, **kwargs)

    sql = (
        "SELECT name FROM artists"
        if failure == "success"
        else "SELECT 'SYNTHETIC-SECRET' FROM missing_table"
    )
    model = Model(
        responses=[
            AIMessage(
                content="", tool_calls=[{"name": "sql_db_query", "args": {"query": sql}, "id": "q"}]
            ),
            AIMessage(content="done"),
        ]
    )
    result = ApplicationService.run(
        "q", "ollama", mode="sql", context=AgentContext(db_uri=uri), llm_factory=lambda **kw: model
    )
    assert result.ok == (failure == "success")
    assert tracked_connections and all(c.closed for c in tracked_connections)
    assert "SYNTHETIC-SECRET" not in str(result) + caplog.text


def test_all_toolkit_observations_bounded(database):
    from langchain_core.language_models.fake import FakeListLLM

    from intellectaengine.core.sql_policy import PolicySQLDatabase
    from intellectaengine.tools.sql_tool import BoundedSQLToolkit

    root, _, uri = database
    db = PolicySQLDatabase(uri, policy(root, sql_observation_char_limit=256))
    tools = {
        t.name: t
        for t in BoundedSQLToolkit(db=db, llm=FakeListLLM(responses=["x" * 1000])).get_tools()
    }
    output = tools["sql_db_query_checker"].invoke({"query": "SELECT 1"})
    assert len(output) == 256 and output.endswith("[truncated]")
    # Repeated names cannot inflate schema output past the same ceiling.
    output = tools["sql_db_schema"].invoke({"table_names": ",".join(["artists"] * 100)})
    assert len(output) <= 256 and output.endswith("[truncated]")
    assert len(tools["sql_db_list_tables"].invoke({"tool_input": ""})) <= 256


@pytest.mark.parametrize("mode", ["sql", "auto"])
@pytest.mark.parametrize("fails", [False, True])
def test_sql_native_tool_calls_commit_exactly_once_in_ui(
    database, project_root, monkeypatch, mode, fails
):
    from langchain_core.callbacks import BaseCallbackHandler
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.messages import AIMessage
    from streamlit.testing.v1 import AppTest

    import intellectaengine.core.sql_policy as module
    from intellectaengine.core.llm_factory import LLMFactory
    from intellectaengine.ui.session_state import SessionStateManager as K

    root, path, uri = database
    monkeypatch.setattr(module, "settings", policy(root, sql_top_k=1).config)
    before = path.read_bytes()
    incoming = []

    class Recorder(BaseCallbackHandler):
        def on_chat_model_start(self, serialized, messages, **kwargs):
            incoming.extend(messages)

    class Model(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    statement = "DELETE FROM artists" if fails else "SELECT name FROM artists ORDER BY id"
    responses = [
        AIMessage(
            content="",
            tool_calls=[{"name": "sql_db_query", "args": {"query": statement}, "id": "q"}],
        ),
        AIMessage(content="Ada is the first artist."),
    ]
    if mode == "auto":
        responses.insert(
            0, AIMessage(content="Action: sql_database_query\nAction Input: first artist")
        )
        responses.append(AIMessage(content="Final Answer: Ada is the first artist."))
    model = Model(responses=responses, callbacks=[Recorder()])
    monkeypatch.setattr(LLMFactory, "create", lambda **kwargs: model)
    app = AppTest.from_file(str(project_root / "app.py")).run(timeout=60)
    app.session_state[K.KEY_DB_URI] = uri
    app.session_state[K.KEY_DB_CONNECTED] = True
    if mode == "sql":
        app.selectbox(key=K.KEY_AGENT_MODE).set_value("sql").run()
    app.chat_input[0].set_value("first artist").run(timeout=60)
    assert not app.exception
    transcript = app.session_state[K.KEY_CHAT_MESSAGES]
    assert len(transcript) == 2
    assert [m.content for m in app.session_state[K.KEY_MEMORY].get_history()] == [
        m["content"] for m in transcript
    ]
    assert transcript[0]["content"] == "first artist"
    assert transcript[1]["content"].startswith("⚠️") == fails
    assert path.read_bytes() == before
    if not fails:
        observations = [m.content for batch in incoming for m in batch if m.type == "tool"]
        assert any("Ada" in o and "Lin" not in o and "[truncated]" in o for o in observations)
    else:
        # Neither inner SQL nor outer router may hide the execution failure.
        assert len(incoming) == (2 if mode == "auto" else 1)
    app.run()
    assert len(app.session_state[K.KEY_CHAT_MESSAGES]) == 2
    next(b for b in app.button if b.label == "Undo").click().run()
    assert app.session_state[K.KEY_CHAT_MESSAGES] == []
    assert app.session_state[K.KEY_MEMORY].get_history() == []


def test_sql_reply_is_bounded_before_outer_router_context(database, monkeypatch):
    from langchain_core.callbacks import BaseCallbackHandler
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.messages import AIMessage

    import intellectaengine.core.sql_policy as module
    from intellectaengine.core.application import ApplicationService
    from intellectaengine.core.contracts import AgentContext

    root, _, uri = database
    monkeypatch.setattr(module, "settings", policy(root, sql_observation_char_limit=256).config)
    incoming = []

    class Recorder(BaseCallbackHandler):
        def on_chat_model_start(self, serialized, messages, **kwargs):
            incoming.extend(messages)

    class Model(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    model = Model(
        responses=[
            AIMessage(content="Action: sql_database_query\nAction Input: first artist"),
            AIMessage(content="x" * 2000 + "UNBOUNDED-TAIL"),
            AIMessage(content="Final Answer: done"),
        ],
        callbacks=[Recorder()],
    )
    result = ApplicationService.run(
        "q", "ollama", mode="auto", context=AgentContext(db_uri=uri), llm_factory=lambda **kw: model
    )
    assert result.ok
    final_prompt = str(incoming[-1])
    assert "UNBOUNDED-TAIL" not in final_prompt
    assert "x" * 200 in final_prompt and "[truncated]" in final_prompt
    assert "x" * 257 not in final_prompt
