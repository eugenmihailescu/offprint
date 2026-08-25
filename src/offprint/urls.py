"""URL origin, site-family match, and internal canonical keys."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from offprint.constants import TRACKING_PARAMS
from offprint.errors import UsageError

_UNRESERVED = re.compile(r"%([0-9A-Fa-f]{2})")


def parse_origin(raw: str) -> str:
    """Normalize ``scheme://host[:port]``. Path, query, and fragment are dropped."""
    text = (raw or "").strip()
    parsed = urlparse(text)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise UsageError("origin must be an http(s) URL with a host", url=text or None)
    host = _idna_host(parsed.hostname)
    port = _effective_port(parsed.scheme, parsed.port)
    return _origin_string(parsed.scheme.lower(), host, port)


def same_site_family(a: str, b: str) -> bool:
    """Match www/apex and http/https twins. Does not rewrite stored URLs."""
    pa, pb = urlparse(a), urlparse(b)
    if not pa.hostname or not pb.hostname:
        return False
    if pa.scheme not in ("http", "https") or pb.scheme not in ("http", "https"):
        return False
    return _family_host(pa.hostname) == _family_host(pb.hostname) and _effective_port(
        pa.scheme, pa.port
    ) == _effective_port(pb.scheme, pb.port)


def canonical_key(url: str) -> str:
    """Internal dedupe key. Does not collapse www vs apex."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise UsageError("URL must be http(s) with a host", url=url)
    scheme = parsed.scheme.lower()
    host = _idna_host(parsed.hostname)
    port = _effective_port(scheme, parsed.port)
    path = _normalize_path(parsed.path or "/")
    query = _strip_tracking(parsed.query)
    netloc = host if port is None else f"{host}:{port}"
    return urlunparse((scheme, netloc, path, "", query, ""))


def www_apex_twin(origin: str) -> str | None:
    """Return the www twin of a normalized origin, or the apex twin of a www origin."""
    parsed = urlparse(origin)
    if not parsed.hostname:
        return None
    host = _idna_host(parsed.hostname)
    if host.startswith("www.") and host.count(".") >= 2:
        twin_host = host[4:]
    else:
        twin_host = f"www.{host}"
    port = _effective_port(parsed.scheme, parsed.port)
    return _origin_string(parsed.scheme.lower(), twin_host, port)


def _origin_string(scheme: str, host: str, port: int | None) -> str:
    if port is None:
        return f"{scheme}://{host}"
    return f"{scheme}://{host}:{port}"


def _idna_host(hostname: str) -> str:
    host = hostname.strip().rstrip(".").lower()
    try:
        return host.encode("idna").decode("ascii")
    except UnicodeError:
        return host


def _family_host(hostname: str) -> str:
    host = _idna_host(hostname)
    if host.startswith("www."):
        return host[4:]
    return host


def _effective_port(scheme: str, port: int | None) -> int | None:
    if port is None:
        return None
    if scheme == "http" and port == 80:
        return None
    if scheme == "https" and port == 443:
        return None
    return port


def _normalize_path(path: str) -> str:
    decoded = _decode_unreserved(path)
    if decoded in ("", "/"):
        return "/"
    return decoded.rstrip("/") or "/"


def _decode_unreserved(path: str) -> str:
    def repl(match: re.Match[str]) -> str:
        raw = bytes.fromhex(match.group(1))
        try:
            ch = raw.decode("ascii")
        except UnicodeDecodeError:
            return match.group(0)
        if ch.isalnum() or ch in "-._~":
            return ch
        return match.group(0)

    return _UNRESERVED.sub(repl, path)


def _strip_tracking(query: str) -> str:
    if not query:
        return ""
    kept = [
        (k, v)
        for k, v in parse_qsl(query, keep_blank_values=True)
        if k.lower() not in TRACKING_PARAMS
    ]
    return urlencode(kept, doseq=True)
