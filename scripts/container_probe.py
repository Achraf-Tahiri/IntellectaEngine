"""Offline checks inside the runtime image; supplied on stdin, never installed."""

import hashlib
from importlib import metadata
from importlib.resources import files
import json
import os
from pathlib import Path
import socket
import sys


# Block Internet sockets before importing application/dependency modules. The
# container also uses --network=none; Unix sockets support AppTest's event loop.
original_socket = socket.socket


class OfflineSocket(original_socket):
    def __init__(self, family=socket.AF_INET, *args, **kwargs):
        assert family == socket.AF_UNIX, "Application attempted an Internet socket"
        super().__init__(family, *args, **kwargs)


def no_network(*args, **kwargs):
    raise AssertionError("Application attempted network access")


def main():
    socket.socket = OfflineSocket
    socket.create_connection = no_network
    socket.getaddrinfo = no_network

    assert os.getuid() == os.getgid() == 10001
    assert Path.cwd() == Path("/app")
    assert not Path(".env").exists()
    assert b"streamlit" in Path("/proc/1/cmdline").read_bytes()
    assert "Uid:\t10001\t10001\t10001\t10001" in Path("/proc/1/status").read_text()

    distribution = metadata.distribution("intellectaengine")
    direct = json.loads(distribution.read_text("direct_url.json"))
    assert direct["url"].endswith(".whl") and not direct.get("dir_info", {}).get("editable")
    for name in ("pytest", "pytest-socket", "ruff", "pip-audit"):
        try:
            metadata.distribution(name)
        except metadata.PackageNotFoundError:
            pass
        else:
            raise AssertionError(f"Development tool in runtime: {name}")

    from intellectaengine.config.settings import settings
    from intellectaengine.core.application import ApplicationService
    from intellectaengine.core.contracts import ErrorCode
    from intellectaengine.core.embedding_factory import EmbeddingFactory
    from intellectaengine.core.llm_factory import LLMFactory
    from intellectaengine.core.sql_policy import SAMPLE_DB, SQLitePolicy

    assert not any((settings.google_api_key, settings.groq_api_key, settings.openai_api_key))
    assert settings.chroma_persist_base_dir == "/data/chroma"
    # Startup must not initialize models even if a dependency would swallow a
    # socket error. Count attempts as well as raising.
    model_attempts = []

    def no_model(*args, **kwargs):
        model_attempts.append(True)
        raise AssertionError("Model construction during startup")

    EmbeddingFactory.create = no_model
    LLMFactory._build = no_model
    assert (
        ApplicationService.run("hello", "gemini", mode="chat").error
        == ErrorCode.INVALID_CONFIGURATION
    )
    sample = files("intellectaengine").joinpath("assets", "Chinook.db")
    digest = "84f5d9143ac4deebdb81650ab650e226d909e660106846b119a5c47c33f94c13"
    assert hashlib.sha256(sample.read_bytes()).hexdigest() == digest
    policy = SQLitePolicy()
    assert len(policy.schema(SAMPLE_DB)) == 11
    assert policy.query(SAMPLE_DB, 'SELECT COUNT(*) FROM "Artist"').strip() == "(275)"
    assert hashlib.sha256(sample.read_bytes()).hexdigest() == digest
    assert not os.access(str(sample), os.W_OK)

    from streamlit import config
    from streamlit.testing.v1 import AppTest
    from streamlit.web import bootstrap, cli

    # Non-sensitive Streamlit environment options are parsed by Click, not by
    # a bare config/AppTest import. Use the real server argv and this container's
    # environment rather than setting the expected values in the test.
    server_argv = Path("/proc/1/cmdline").read_bytes().rstrip(b"\0").decode().split("\0")
    with cli.main_run.make_context("run", server_argv[server_argv.index("run") + 1 :]) as ctx:
        bootstrap.load_config_options(
            {key: value for key, value in ctx.params.items() if key not in ("target", "args")}
        )

    assert config.get_option("server.enableCORS") is True
    assert config.get_option("server.enableXsrfProtection") is True
    assert config.get_option("browser.gatherUsageStats") is False
    assert config.get_option("theme.primaryColor") == "#8B5CF6"
    assert config.get_option("server.address") == "0.0.0.0"
    assert config.get_option("server.port") == 8501
    assert config.get_option("server.headless") is True
    app = AppTest.from_file(str(files("intellectaengine").joinpath("streamlit_app.py")))
    app.run(timeout=60)
    assert not app.exception, app.exception
    assert len(app.chat_input) == 1
    assert any("GOOGLE_API_KEY" in warning.value for warning in app.warning)
    assert not model_attempts
    if sys.argv[1] == "write":
        assert not list(Path(settings.chroma_persist_base_dir).iterdir()), (
            "Startup initialized Chroma storage"
        )

    cache = Path(os.environ["XDG_CACHE_HOME"])
    assert not [p for p in cache.rglob("*") if p.is_file() and p.name != "phase8-synthetic"], (
        "Startup wrote unexpected cache/model files"
    )
    import chromadb
    from chromadb.config import Settings

    client = chromadb.PersistentClient(
        path=settings.chroma_persist_base_dir, settings=Settings(anonymized_telemetry=False)
    )
    mode = sys.argv[1]
    if mode == "write":
        collection = client.create_collection("phase8-synthetic", embedding_function=None)
        collection.add(
            ids=["synthetic"], embeddings=[[1.0, 0.0, 0.0]], documents=["synthetic data"]
        )
    else:
        collection = client.get_collection("phase8-synthetic", embedding_function=None)
        result = collection.get(ids=["synthetic"], include=["documents", "embeddings"])
        assert result["documents"] == ["synthetic data"]
        assert result["embeddings"].tolist() == [[1.0, 0.0, 0.0]]

    for name in (
        "HOME",
        "CHROMA_PERSIST_BASE_DIR",
        "XDG_CACHE_HOME",
        "HF_HOME",
        "SENTENCE_TRANSFORMERS_HOME",
        "FASTEMBED_CACHE_PATH",
    ):
        directory = Path(os.environ[name])
        directory.mkdir(parents=True, exist_ok=True)
        marker = directory / "phase8-synthetic"
        if mode == "read" and name != "HOME":
            assert marker.read_text() == "synthetic persistence probe"
        marker.write_text("synthetic persistence probe")
    print(
        f"PASS: non-root, installed wheel, offline UI/SQL, cache paths, Chroma {mode}", flush=True
    )


if __name__ == "__main__":
    main()
