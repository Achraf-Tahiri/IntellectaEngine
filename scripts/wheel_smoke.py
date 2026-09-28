"""Run with the wheel environment's Python -I, from an empty temporary cwd."""

import hashlib
from importlib import import_module, metadata
from importlib.resources import files
import json
from pathlib import Path
import sys

from pytest_socket import disable_socket


def main():
    disable_socket(allow_unix_socket=True)
    prefix = Path(sys.prefix).resolve()
    checkout = Path(sys.argv[1]).resolve()
    assert not Path.cwd().is_relative_to(checkout)
    assert not any(Path(p).resolve().is_relative_to(checkout) for p in sys.path if p)

    for name in ("", ".config", ".core", ".connectors", ".tools", ".ui", ".streamlit_app"):
        module = import_module("intellectaengine" + name)
        assert Path(module.__file__).resolve().is_relative_to(prefix), module.__file__
    assert not any(
        name in sys.modules
        for name in (
            "streamlit",
            "torch",
            "chromadb",
            "langchain_google_genai",
            "pydantic_settings",
        )
    )
    distribution = metadata.distribution("intellectaengine")
    direct = json.loads(distribution.read_text("direct_url.json"))
    assert not direct.get("dir_info", {}).get("editable", False)
    assert direct["url"].endswith(".whl")
    for notice in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        assert any(str(p).endswith("/licenses/" + notice) for p in distribution.files)
    print("Wheel import:", files("intellectaengine"))

    from intellectaengine.core.application import ApplicationService
    from intellectaengine.core.contracts import ErrorCode
    from intellectaengine.core.sql_policy import SAMPLE_DB, SQLitePolicy
    from intellectaengine.config.settings import settings

    assert "streamlit" not in sys.modules
    assert not any((settings.google_api_key, settings.groq_api_key, settings.openai_api_key))
    assert settings.chroma_persist_base_dir == "./data/chroma"
    result = ApplicationService.run("hello", "gemini", mode="chat")
    assert result.error == ErrorCode.INVALID_CONFIGURATION

    sample = files("intellectaengine").joinpath("assets", "Chinook.db")
    digest = hashlib.sha256(sample.read_bytes()).hexdigest()
    assert digest == "84f5d9143ac4deebdb81650ab650e226d909e660106846b119a5c47c33f94c13"
    policy = SQLitePolicy()
    assert len(policy.schema(SAMPLE_DB)) == 11
    assert policy.query(SAMPLE_DB, 'SELECT COUNT(*) FROM "Artist"').strip() == "(275)"
    assert hashlib.sha256(sample.read_bytes()).hexdigest() == digest

    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(files("intellectaengine").joinpath("streamlit_app.py")))
    app.run(timeout=60)
    assert not app.exception, app.exception
    assert len(app.chat_input) == 1
    assert any("GOOGLE_API_KEY" in warning.value for warning in app.warning)
    assert not list(Path.cwd().iterdir()), "Startup created runtime files"
    assert {p.name for p in sample.parent.iterdir()} == {"Chinook.db"}
    print("Headless dispatch, read-only Chinook, and initial Streamlit render passed offline")


if __name__ == "__main__":
    main()
