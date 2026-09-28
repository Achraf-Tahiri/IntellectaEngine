"""Local lexical URL policy and bounded display helpers; no DNS claims."""

import html
import ipaddress
import re
import unicodedata
from urllib.parse import quote, urlsplit, urlunsplit

from intellectaengine.core.contracts import ApplicationError, ErrorCode

MARKER = "\n[truncated]"


def fail():
    raise ApplicationError(ErrorCode.TOOL_FAILURE) from None


def text_input(value, limit):
    if not isinstance(value, str) or len(value) > limit or not value.strip():
        fail()
    if any(unicodedata.category(c).startswith("C") for c in value):
        fail()
    return value.strip()


def lower_limit(value, ceiling, minimum=1):
    if value is None:
        return ceiling
    if type(value) is not int or not minimum <= value <= ceiling:
        fail()
    return value


def target_url(value, limit):
    """Reject ambiguous authorities; normalize only scheme/IDNA host, not path/query."""
    value = text_input(value, limit)
    try:
        if any(c.isspace() for c in value) or "\\" in value:
            fail()
        parts = urlsplit(value)
        authority = parts.netloc
        if parts.scheme not in {"http", "https"} or not authority:
            fail()
        if any(c in authority for c in "@%"):
            fail()
        host = parts.hostname
        if not host or host.endswith("."):
            fail()
        # Only the default port for each scheme; no empty, signed or padded ports.
        port = ":80" if parts.scheme == "http" else ":443"
        if authority.startswith("["):
            close = authority.find("]")
            if close < 0 or authority[close + 1 :] not in {"", port}:
                fail()
            address = ipaddress.IPv6Address(host)
            if (
                not address.is_global
                or address.is_reserved
                or address.is_site_local
                or address.ipv4_mapped is not None
                or address.is_multicast
            ):
                fail()
            # Transition mechanisms have additional embedded-address semantics.
            if address.sixtofour is not None or address.teredo is not None:
                fail()
            safe_host = f"[{address.compressed}]"
        else:
            if authority.count(":") > 1 or (":" in authority and not authority.endswith(port)):
                fail()
            safe_host = host.encode("idna").decode("ascii").lower()
            try:
                address = ipaddress.IPv4Address(safe_host)
            except ValueError:
                labels = safe_host.split(".")
                # Numeric final labels cover inet_aton integer, octal, hex and short forms.
                if re.fullmatch(r"(?:[0-9]+|0x[0-9a-f]+)", labels[-1]):
                    fail()
                if len(labels) < 2 or len(safe_host) > 253:
                    fail()
                if any(
                    not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", p) for p in labels
                ):
                    fail()
                if labels[-1] in {
                    "localhost",
                    "localdomain",
                    "private",
                    "arpa",
                    "local",
                    "internal",
                    "intranet",
                    "lan",
                    "home",
                    "corp",
                    "test",
                    "invalid",
                    "onion",
                }:
                    fail()
            else:
                if host != safe_host or not address.is_global or address.is_multicast:
                    fail()
        suffix = port if authority.endswith(port) else ""
        # Invalid percent escapes must not be silently repaired by the HTTP client.
        if re.search(r"%(?![0-9a-fA-F]{2})", parts.path + parts.query + parts.fragment):
            fail()
        result = urlunsplit(
            (parts.scheme, safe_host + suffix, parts.path, parts.query, parts.fragment)
        )
        if len(result) > limit:
            fail()
        return result
    except (ValueError, UnicodeError):
        fail()


def bounded(text, limit, truncated=False):
    if len(text) > limit or truncated:
        return text[: limit - len(MARKER)] + MARKER
    return text


def display(text, limit):
    """Render provider text literally, with work bounded before escaping."""
    text = bounded(text, limit)
    text = "".join(
        c if not unicodedata.category(c).startswith("C") or c in "\n\t" else " " for c in text
    )
    text = html.escape(text, quote=True)
    text = re.sub(r"([\\`*_{}\[\]()#+.!|~>-])", r"\\\1", text)
    return bounded(text, limit)


def source_link(url, limit=800):
    # Quote Markdown/HTML delimiters without changing existing URL escapes.
    encoded = quote(url, safe=":/?#[]@!$&'*+,;=%~_-.")
    if len(encoded) > limit:
        return "Source URL omitted (display limit)."
    return f"[Source](<{encoded}>)"
