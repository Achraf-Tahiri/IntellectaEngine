"""Keep baseline tests independent of developer credentials and model caches."""

import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_configuration(monkeypatch, tmp_path):
    # Settings load .env relative to cwd. Change it before importing application
    # modules; never load or edit the developer's private file.
    monkeypatch.chdir(tmp_path)
    example = Path(__file__).resolve().parents[1] / ".env.example"
    setting_names = {
        line.split("=", 1)[0].strip().upper()
        for line in example.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#") and "=" in line
    }
    for name in list(os.environ):
        if name.upper() in setting_names or name.upper().startswith(
            ("LANGCHAIN_", "LANGSMITH_", "HF_", "HUGGINGFACE_")
        ):
            monkeypatch.delenv(name)
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    monkeypatch.setenv("HF_HOME", str(tmp_path / "huggingface"))
    monkeypatch.setenv("LANGSMITH_TRACING", "false")


@pytest.fixture
def project_root():
    return Path(__file__).resolve().parents[1]


@pytest.fixture
def web_network(monkeypatch):
    """Real Requests session/response lifecycle, fake transport; sockets stay blocked."""
    import io
    import logging
    from types import SimpleNamespace

    import requests
    from requests.adapters import BaseAdapter
    from urllib3.response import HTTPResponse

    import intellectaengine.tools.web_research_tool as web

    state = SimpleNamespace(
        body=b"Offline page evidence",
        status=200,
        headers={"Content-Type": "text/plain; charset=utf-8"},
        failure=None,
        read_failure=None,
        calls=[],
        sessions=[],
        responses=[],
        reads=[],
        adapter_closes=0,
        response_closes=0,
    )

    class Raw(HTTPResponse):
        def read(self, amt=None, decode_content=None, **kwargs):
            assert amt is not None and amt > 0
            assert decode_content is False
            state.reads.append(amt)
            if state.read_failure:
                raise state.read_failure
            return super().read(amt, decode_content=decode_content, **kwargs)

    class Response(requests.Response):
        @property
        def text(self):
            raise AssertionError("Unbounded text access")

        @property
        def content(self):
            raise AssertionError("Unbounded content access")

        def close(self):
            state.response_closes += 1
            super().close()

    class Adapter(BaseAdapter):
        def send(self, request, **kwargs):
            state.calls.append((request, kwargs))
            # Match the installed urllib3 response diagnostic's argument layout.
            logging.getLogger("urllib3.connectionpool").debug(
                '%s://%s:%s "%s %s %s" %s %s',
                "https",
                "r.jina.ai",
                443,
                "GET",
                request.path_url,
                "HTTP/1.1",
                state.status,
                len(state.body),
            )
            if state.failure:
                raise state.failure
            response = Response()
            response.status_code = state.status
            response.headers.update(state.headers)
            response.raw = Raw(body=io.BytesIO(state.body), preload_content=False)
            response.url = request.url
            response.request = request
            state.responses.append(response)
            return response

        def close(self):
            state.adapter_closes += 1

    original = requests.Session

    def session():
        value = original()
        value.mount("https://", Adapter())
        state.sessions.append(value)
        return value

    monkeypatch.setattr(web.requests, "Session", session)
    return state


@pytest.fixture
def web_search(monkeypatch):
    """Model DDGS.text's list return and the actual nested primp context protocol."""
    import logging
    from types import SimpleNamespace

    import intellectaengine.tools.web_research_tool as web

    state = SimpleNamespace(
        results=[
            {
                "title": "Offline title",
                "href": "https://example.com/page",
                "body": "Offline snippet",
            }
        ],
        failure=None,
        calls=[],
        constructors=[],
        closed=0,
        ddgs_exits=0,
    )

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            state.closed += 1

    class Search:
        def __init__(self, **kwargs):
            state.constructors.append(kwargs)
            self.client = Client()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            state.ddgs_exits += 1

        def text(self, query, **kwargs):
            state.calls.append((query, kwargs))
            if state.failure:
                logging.getLogger("duckduckgo_search.duckduckgo_search").info(
                    "Provider exception: %s", state.failure
                )
                raise state.failure
            return state.results

    monkeypatch.setattr(web, "DDGS", Search)
    return state
