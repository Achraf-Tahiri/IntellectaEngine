"""Installation boundaries, resource lifetime, and the small Streamlit launcher."""

from contextlib import contextmanager
from importlib.resources import as_file
import logging
from pathlib import Path
import sqlite3
import subprocess
import sys
import zipfile

import pytest


def test_package_initializers_and_launcher_are_lightweight():
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            "import intellectaengine, intellectaengine.config, intellectaengine.core, "
            "intellectaengine.connectors, intellectaengine.tools, intellectaengine.ui, "
            "intellectaengine.streamlit_app; import sys; "
            "assert not any(n.split('.')[0] in "
            "{'streamlit', 'torch', 'chromadb', 'langchain_google_genai', "
            "'sentence_transformers', 'pydantic_settings'} for n in sys.modules)",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("outcome", [SystemExit(23), KeyboardInterrupt()])
def test_launcher_execs_same_interpreter_and_preserves_arguments(monkeypatch, outcome):
    from intellectaengine import streamlit_app

    options = ["--server.port=8507", "--server.headless", "true", "--", "a b", "$(literal)"]
    monkeypatch.setattr(sys, "argv", ["intellectaengine", *options])
    calls = []

    def execute(executable, arguments):
        calls.append((executable, arguments))
        raise outcome

    monkeypatch.setattr(streamlit_app.os, "execv", execute)
    with pytest.raises(type(outcome)) as raised:
        streamlit_app.launch()
    assert raised.value is outcome
    assert calls == [
        (
            sys.executable,
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                str(Path(streamlit_app.__file__).with_name("streamlit_app.py")),
                *options,
            ],
        )
    ]


@pytest.mark.parametrize("outcome", ["success", "failure", "interrupt"])
def test_extracted_sample_lives_until_connection_closes(monkeypatch, tmp_path, outcome):
    import intellectaengine.core.sql_policy as sql
    from intellectaengine.core.contracts import ApplicationError, ErrorCode

    archive = tmp_path / "resource.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("Chinook.db", sql.CHINOOK_DB_RESOURCE.read_bytes())
    connections = []
    extracted = []
    original_connect = sqlite3.connect

    def connect(database, **kwargs):
        assert database.endswith("?mode=ro") and kwargs["uri"]
        conn = original_connect(database, **kwargs)
        connections.append(conn)
        return conn

    @contextmanager
    def resource_path(resource):
        with as_file(resource) as path:
            extracted.append(path)
            try:
                yield path
            finally:
                assert path.is_file()
                with pytest.raises(sqlite3.ProgrammingError, match="closed"):
                    connections[-1].execute("SELECT 1")

    monkeypatch.setattr(sql.sqlite3, "connect", connect)
    monkeypatch.setattr(sql, "as_file", resource_path)
    with zipfile.ZipFile(archive) as zipped:
        monkeypatch.setattr(sql, "CHINOOK_DB_RESOURCE", zipfile.Path(zipped, "Chinook.db"))
        policy = sql.SQLitePolicy()
        if outcome == "success":
            assert policy.query(sql.SAMPLE_DB, 'SELECT COUNT(*) FROM "Artist"').strip() == "(275)"
        elif outcome == "failure":
            with pytest.raises(ApplicationError) as raised:
                policy.query(sql.SAMPLE_DB, "SELECT * FROM absent_table")
            assert raised.value.code == ErrorCode.TOOL_FAILURE
        else:
            with pytest.raises(KeyboardInterrupt):
                with policy.connection(sql.SAMPLE_DB):
                    raise KeyboardInterrupt
    assert len(connections) == len(extracted) == 1
    assert not extracted[0].exists()


def test_locked_streamlit_watcher_handles_unmodified_torch_classes(caplog):
    import torch
    from streamlit.watcher.local_sources_watcher import get_module_paths

    # This regression check intentionally exercises the dependency's watcher.
    # Older versions incorrectly inspected torch.classes.__path__._path.
    assert type(torch.classes.__path__).__name__ == "_ClassNamespace"
    with caplog.at_level(logging.WARNING, logger="streamlit.watcher.local_sources_watcher"):
        assert get_module_paths(torch.classes) == set()
    assert not caplog.records
