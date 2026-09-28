"""Offline resource, URL, display, and lifecycle contracts for web evidence."""

import logging

import pytest


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "http://example.com:80/a%2Fb?q=a%26b&x=1+2#part",
        "https://example.com:443/a(b)",
        "https://8.8.8.8/path",
        "https://[2606:4700:4700::1111]/",
        "https://bücher.de/é?q=%25",
    ],
)
def test_valid_targets(url):
    from intellectaengine.core.web_policy import target_url
    from urllib.parse import urlsplit

    normalized = target_url(url, 2048)
    assert urlsplit(normalized).path == urlsplit(url).path
    assert urlsplit(normalized).query == urlsplit(url).query


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com",
        "//example.com",
        "https:example.com",
        "https:///example.com",
        "https://u:p@example.com",
        "https://@example.com",
        "https://example.com\\@evil.com",
        "https://exa\nmple.com",
        "https://example.com/\x00",
        "http://localhost",
        "http://LOCALHOST.",
        "http://printer",
        "http://a.local",
        "http://a.localhost",
        "http://a.internal",
        "http://a.localdomain",
        "http://a.home.arpa",
        "http://127.0.0.1",
        "http://0.0.0.0",
        "http://10.0.0.1",
        "http://169.254.169.254",
        "http://100.64.0.1",
        "http://192.168.1.1",
        "http://224.0.0.1",
        "http://192.0.2.1",
        "http://127.1",
        "http://2130706433",
        "http://0177.0.0.1",
        "http://0x7f000001",
        "http://0x7f.0.0.1",
        "http://127.0.0.01",
        "http://0x08080808",
        "http://8.8.8",
        "http://[4000::1]",
        "http://[fec0::1]",
        "http://[64:ff9b::7f00:1]",
        "http://[::8.8.8.8]",
        "http://[::1]",
        "http://[::]",
        "http://[fc00::1]",
        "http://[fe80::1]",
        "http://[::ffff:127.0.0.1]",
        "http://[::ffff:8.8.8.8]",
        "http://[ff02::1]",
        "http://[2002:0808:0808::1]",
        "http://[fe80::1%25eth0]",
        "http://example.com:443",
        "https://example.com:80",
        "https://example.com:8080",
        "https://example.com:",
        "https://example.com:+443",
        "https://example.com:0443",
        "https://example.com:443:443",
        "https://[::1",
        "https://[2606:4700::1111]evil",
        "https://example.com.",
        "https://%65xample.com",
        "https://a..com",
        "https://-a.com",
        "https://a_b.com",
        "https://example.com/%ZZ",
        "https://example.com/a b",
    ],
)
def test_rejected_targets_never_reach_transport(url, web_network):
    from intellectaengine.core.contracts import ApplicationError
    from intellectaengine.tools.web_research_tool import WebResearchTool

    for call in (
        lambda: WebResearchTool.scrape(url),
        lambda: WebResearchTool.run("SCRAPE:" + url),
        lambda: WebResearchTool.as_structured_tool().invoke({"query": "SCRAPE:" + url}),
    ):
        with pytest.raises(ApplicationError):
            call()
    assert not web_network.sessions


@pytest.mark.parametrize("value", [None, 123, True, [], "", " ", "q\x00", "q" * 1001])
def test_query_validation_all_entry_points(value, web_search):
    from intellectaengine.core.contracts import ApplicationError
    from intellectaengine.tools.web_research_tool import WebResearchTool

    for call in (
        lambda: WebResearchTool.search(value),
        lambda: WebResearchTool.run(value),
        lambda: WebResearchTool.as_structured_tool().invoke({"query": value}),
    ):
        with pytest.raises(ApplicationError):
            call()
    assert not web_search.constructors


def test_schema_and_url_length_failures_are_safe(web_network):
    from intellectaengine.core.contracts import ApplicationError
    from intellectaengine.tools.web_research_tool import WebResearchTool

    for value in (
        {"secret": "SYNTHETIC-SECRET"},
        {"query": "q", "extra": "secret"},
        {"query": "SCRAPE:https://example.com/" + "x" * 2048},
    ):
        with pytest.raises(ApplicationError) as exc:
            WebResearchTool.as_structured_tool().invoke(value)
        assert "SECRET" not in str(exc.value)
    assert not web_network.sessions


def test_fixed_reader_origin_and_explicit_transport(web_network, monkeypatch):
    import requests.sessions
    from intellectaengine.tools.web_research_tool import WebResearchTool

    monkeypatch.setenv("HTTPS_PROXY", "http://user:secret@localhost:9999")
    monkeypatch.setenv("NETRC", "/not/used")
    monkeypatch.setattr(requests.sessions, "get_netrc_auth", lambda *a: pytest.fail("netrc read"))
    result = WebResearchTool.scrape("https://example.com/a%2Fb?q=a%26b&x=1+2")
    request, kwargs = web_network.calls[0]
    assert request.url == "https://r.jina.ai/https://example.com/a%2Fb?q=a%26b&x=1+2"
    assert kwargs["stream"] is True and kwargs["verify"] is True
    assert kwargs["timeout"] == (5, 15) and not kwargs["proxies"]
    assert "Authorization" not in request.headers and "Cookie" not in request.headers
    assert request.headers["Accept-Encoding"] == "identity"
    assert "Mozilla" not in request.headers["User-Agent"]
    assert not web_network.sessions[0].trust_env
    assert "Offline page evidence" in result
    assert web_network.response_closes == web_network.adapter_closes == 1


@pytest.mark.parametrize("length", [None, "1", "9999999", "invalid"])
def test_stream_overflow_ignores_content_length(web_network, monkeypatch, length):
    import intellectaengine.tools.web_research_tool as web

    monkeypatch.setattr(web.settings, "web_response_byte_limit", 32)
    web_network.body = b"A" * 10000
    if length is not None:
        web_network.headers["Content-Length"] = length
    result = web.WebResearchTool.scrape("https://example.com")
    assert result.endswith("[truncated]")
    assert "A" * 32 in result
    assert sum(web_network.reads) == 33
    assert web_network.response_closes == web_network.adapter_closes == 1


@pytest.mark.parametrize("status", [301, 302, 307, 308, 400, 403, 429, 500])
def test_endpoint_redirects_and_http_errors(web_network, status):
    from intellectaengine.core.contracts import ApplicationError
    from intellectaengine.tools.web_research_tool import WebResearchTool

    web_network.status = status
    web_network.headers["Location"] = "http://localhost/SYNTHETIC-SECRET"
    with pytest.raises(ApplicationError):
        WebResearchTool.scrape("https://example.com")
    assert len(web_network.calls) == 1 and not web_network.reads
    assert web_network.response_closes == web_network.adapter_closes == 1


@pytest.mark.parametrize(
    "body,ctype,expected",
    [
        ("café".encode(), "text/plain; charset=utf-8", "café"),
        (b"caf\xe9", "text/plain; charset=iso-8859-1", "café"),
        (b"<script>alert(1)</script>", "text/html", "&lt;script&gt;"),
        (b"readable", "text/markdown", "readable"),
    ],
)
def test_text_decoding_and_safe_display(web_network, body, ctype, expected):
    from intellectaengine.tools.web_research_tool import WebResearchTool

    web_network.body = body
    web_network.headers["Content-Type"] = ctype
    assert expected in WebResearchTool.scrape("https://example.com")


@pytest.mark.parametrize(
    "body,headers",
    [
        (b"", {"Content-Type": "text/plain"}),
        (b" \n", {"Content-Type": "text/plain"}),
        (b"\x00PNG", {"Content-Type": "text/plain"}),
        (b"\xff", {"Content-Type": "text/plain"}),
        (b"hi", {"Content-Type": "image/png"}),
        (b"hi", {}),
        (b"hi", {"Content-Type": "garbage"}),
        (b"hi", {"Content-Type": 'text/plain; charset="utf-8'}),
        (b"hi", {"Content-Type": "text/plain; charset=utf-8; charset=ascii"}),
        (b"hi", {"Content-Type": "text/plain; charset=bogus"}),
        (b"hi", {"Content-Type": "text/plain", "Content-Encoding": "gzip"}),
    ],
)
def test_empty_binary_malformed_responses(web_network, body, headers):
    from intellectaengine.core.contracts import ApplicationError
    from intellectaengine.tools.web_research_tool import WebResearchTool

    web_network.body, web_network.headers = body, headers
    with pytest.raises(ApplicationError):
        WebResearchTool.scrape("https://example.com")
    assert web_network.response_closes == web_network.adapter_closes == 1


@pytest.mark.parametrize("stage", ["connect", "read"])
@pytest.mark.parametrize("interrupt", [False, True])
def test_network_failures_and_interruptions_close_resources(web_network, stage, interrupt, caplog):
    import requests
    from intellectaengine.core.contracts import ApplicationError
    from intellectaengine.tools.web_research_tool import WebResearchTool

    caplog.set_level(logging.DEBUG)
    error = (
        KeyboardInterrupt("SYNTHETIC-SECRET") if interrupt else requests.Timeout("SYNTHETIC-SECRET")
    )
    setattr(web_network, "failure" if stage == "connect" else "read_failure", error)
    with pytest.raises(KeyboardInterrupt if interrupt else ApplicationError) as exc:
        WebResearchTool.scrape("https://example.com/?secret=SYNTHETIC-SECRET")
    assert web_network.adapter_closes == 1
    assert web_network.response_closes == (stage == "read")
    if not interrupt:
        assert "SYNTHETIC-SECRET" not in str(exc.value) + caplog.text


def test_elapsed_budget(web_network, monkeypatch):
    import intellectaengine.tools.web_research_tool as web
    from intellectaengine.core.contracts import ApplicationError

    ticks = iter([0, 0, 31])
    monkeypatch.setattr(web, "monotonic", lambda: next(ticks))
    with pytest.raises(ApplicationError):
        web.WebResearchTool.scrape("https://example.com")
    assert web_network.response_closes == web_network.adapter_closes == 1


@pytest.mark.parametrize("limit", [128, 256, 6000])
def test_exact_observation_bound(web_network, limit):
    from intellectaengine.tools.web_research_tool import WebResearchTool

    web_network.body = b"A" * 10000
    result = WebResearchTool.scrape("https://example.com/" + "x" * 700, max_chars=limit)
    assert len(result) == limit and result.endswith("[truncated]")
    assert result.count("[Source](<") == result.count(">)")


def test_multibyte_overflow_not_a_decode_error(web_network, monkeypatch):
    import intellectaengine.tools.web_research_tool as web

    web_network.body = "café".encode()
    monkeypatch.setattr(web.settings, "web_response_byte_limit", 4)
    result = web.WebResearchTool.scrape("https://example.com")
    assert "caf" in result and result.endswith("[truncated]")


@pytest.mark.parametrize("override", [0, -1, True, 1.5, "2", 21])
def test_bad_overrides_never_construct_clients(web_network, web_search, override):
    from intellectaengine.core.contracts import ApplicationError
    from intellectaengine.tools.web_research_tool import WebResearchTool

    for call in (
        lambda: WebResearchTool.search("q", override),
        lambda: WebResearchTool.scrape("https://example.com", timeout=override),
        lambda: WebResearchTool.scrape("https://example.com", max_chars=override),
    ):
        with pytest.raises(ApplicationError):
            call()
    assert not web_network.sessions and not web_search.constructors


def test_search_passes_controls_consumes_only_cap_and_closes(web_search):
    from intellectaengine.tools.web_research_tool import WebResearchTool

    entry = web_search.results[0]

    def bounded_results():
        yield entry
        yield entry
        pytest.fail("Consumed beyond the requested cap")

    web_search.results = bounded_results()
    assert "Offline title" in WebResearchTool.search("q", max_results=2)
    assert web_search.constructors == [{"timeout": 15, "verify": True}]
    assert web_search.calls == [("q", {"max_results": 2, "backend": "html"})]
    assert web_search.closed == web_search.ddgs_exits == 1


@pytest.mark.parametrize(
    "results",
    [
        None,
        "bad",
        {},
        [None, 123, []],
        [{"title": "title", "href": "javascript:alert(1)"}],
        [{"title": [], "href": "https://example.com"}],
        [{"title": "", "body": "", "href": "https://example.com"}],
        [{"title": "title"}],
        [{"title": "title", "href": "http://127.1"}],
    ],
)
def test_malformed_search_is_failure(web_search, results):
    from intellectaengine.tools.web_research_tool import WebResearchTool
    from intellectaengine.core.contracts import ApplicationError

    web_search.results = results
    with pytest.raises(ApplicationError):
        WebResearchTool.search("q")
    assert web_search.closed == web_search.ddgs_exits == 1


def test_empty_search_is_success(web_search):
    from intellectaengine.tools.web_research_tool import WebResearchTool

    web_search.results = []
    assert WebResearchTool.search("q") == "No web search results found."
    assert web_search.closed == 1


def test_mixed_results_and_markdown_are_safe(web_search):
    from intellectaengine.tools.web_research_tool import WebResearchTool

    web_search.results = [
        None,
        {
            "title": "![image](https://evil.com) <img src=x>",
            "body": "# heading\n[malicious](javascript:alert(1))",
            "href": "https://example.com/a(b)?x=%26",
        },
        {"body": "Only snippet", "href": "https://example.com"},
    ]
    result = WebResearchTool.search("q")
    assert "Some invalid results were omitted" in result and "Untitled" in result
    assert "![image]" not in result and "<img" not in result
    assert "[Source](<https://example.com/a%28b%29?x=%26>)" in result


def test_search_complete_and_field_bounds(web_search, monkeypatch):
    import intellectaengine.tools.web_research_tool as web

    web_search.results = [
        {"title": "T" * 10000, "body": "B" * 10000, "href": "https://example.com/" + "u" * 1500}
    ] * 5
    result = web.WebResearchTool.search("q")
    assert len(result) <= 6000 and "T" * 241 not in result and "B" * 1001 not in result
    assert "Source URL omitted" in result and result.endswith("[truncated]")
    monkeypatch.setattr(web.settings, "web_observation_char_limit", 128)
    result = web.WebResearchTool.search("q")
    assert len(result) <= 128 and result.endswith("[truncated]")


@pytest.mark.parametrize("interrupt", [False, True])
def test_search_failure_cleanup_and_secret_logs(web_search, interrupt, caplog):
    from intellectaengine.tools.web_research_tool import WebResearchTool
    from intellectaengine.core.contracts import ApplicationError

    caplog.set_level(logging.DEBUG)
    web_search.failure = (
        KeyboardInterrupt("SYNTHETIC-SECRET") if interrupt else RuntimeError("SYNTHETIC-SECRET")
    )
    with pytest.raises(KeyboardInterrupt if interrupt else ApplicationError) as exc:
        WebResearchTool.search("query SYNTHETIC-SECRET")
    assert web_search.closed == web_search.ddgs_exits == 1
    assert "SYNTHETIC-SECRET" not in caplog.text
    if not interrupt:
        assert "SYNTHETIC-SECRET" not in str(exc.value)
