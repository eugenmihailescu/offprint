"""SSRF policy: scheme, host, userinfo, and resolved IP blocklists."""

from __future__ import annotations

import ipaddress
import re
import socket
from collections.abc import Sequence
from urllib.parse import urlparse

from offprint.constants import URL_MAX_LENGTH
from offprint.errors import BlockedUrlError, FetchError

_ALLOWED_SCHEMES = frozenset({"http", "https"})
_BLOCKED_HOST_SUFFIXES = (
    ".localhost",
    ".local",
    ".internal",
    ".intranet",
    ".lan",
    ".home",
    ".arpa",
)
_BLOCKED_HOSTS = frozenset(
    {
        "localhost",
        "metadata",
        "metadata.google.internal",
        "metadata.google.com",
        "kubernetes.default",
        "kubernetes.default.svc",
        "instance-data",
    }
)
_V4_NETWORKS = tuple(
    ipaddress.ip_network(n)
    for n in (
        "0.0.0.0/8",
        "10.0.0.0/8",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "100.64.0.0/10",
        "192.0.0.0/24",
        "192.0.2.0/24",
        "198.18.0.0/15",
        "198.51.100.0/24",
        "203.0.113.0/24",
        "224.0.0.0/4",
        "240.0.0.0/4",
    )
)
_V6_NETWORKS = tuple(
    ipaddress.ip_network(n)
    for n in (
        "::/128",
        "::1/128",
        "fe80::/10",
        "fc00::/7",
        "ff00::/8",
        "2001:db8::/32",
        "64:ff9b::/96",
    )
)
_OCTAL_DOT = re.compile(r"^(?:0[0-7]{0,3}|[0-9]{1,3})(?:\.(?:0[0-7]{0,3}|[0-9]{1,3})){3}$")
_DECIMAL_IP = re.compile(r"^\d+$")


def lookup_host(hostname: str) -> list[str]:
    """DNS helper tests may monkeypatch. Returns unique address strings."""
    infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    seen: list[str] = []
    for info in infos:
        addr = info[4][0]
        if addr not in seen:
            seen.append(addr)
    return seen


def hostname_looks_blocked(hostname: str) -> bool:
    """Name policy after IDNA and trailing-dot strip. Literal IPs use the IP parser."""
    host = _normalize_host(hostname)
    if not host:
        return True
    literal = parse_literal_ip(host)
    if literal is not None:
        return ip_is_blocked(literal)
    if host in _BLOCKED_HOSTS:
        return True
    if "." not in host:
        return True
    return any(host.endswith(suffix) for suffix in _BLOCKED_HOST_SUFFIXES)


def parse_literal_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """Parse dotted, compressed, decimal, or octal IPv4, and IPv6. None if not an IP."""
    text = host.strip().rstrip(".")
    if not text:
        return None
    if ":" in text:
        try:
            return ipaddress.IPv6Address(text)
        except ValueError:
            return None
    if _DECIMAL_IP.fullmatch(text):
        try:
            n = int(text, 10)
        except ValueError:
            return None
        if 0 <= n <= 0xFFFFFFFF:
            return ipaddress.IPv4Address(n)
        return None
    octalish = any(p.startswith("0") and len(p) > 1 for p in text.split("."))
    if _OCTAL_DOT.fullmatch(text) and octalish:
        parts: list[int] = []
        for part in text.split("."):
            base = 8 if part.startswith("0") and len(part) > 1 else 10
            try:
                n = int(part, base)
            except ValueError:
                return None
            if n > 255:
                return None
            parts.append(n)
        return ipaddress.IPv4Address(".".join(str(p) for p in parts))
    try:
        return ipaddress.ip_address(text)
    except ValueError:
        return None


def ip_is_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address):
        mapped = ip.ipv4_mapped
        if mapped is not None:
            return ip_is_blocked(mapped)
        nat64 = ipaddress.IPv6Network("64:ff9b::/96")
        if ip in nat64:
            embedded = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
            return ip_is_blocked(embedded)
        return any(ip in net for net in _V6_NETWORKS)
    return any(ip in net for net in _V4_NETWORKS)


async def assert_public_http_url(raw: str) -> str:
    """Raise ``BlockedUrlError`` / ``FetchError`` if the URL must not be fetched."""
    text = (raw or "").strip()
    if len(text) > URL_MAX_LENGTH:
        raise BlockedUrlError("URL exceeds max length", url=text[:URL_MAX_LENGTH])
    try:
        parsed = urlparse(text)
    except ValueError as exc:
        raise BlockedUrlError("invalid URL", url=text) from exc
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise BlockedUrlError(f"unsupported scheme: {parsed.scheme or '(none)'}", url=text)
    if parsed.username is not None or parsed.password is not None:
        raise BlockedUrlError("URL must not include credentials", url=text)
    host = parsed.hostname
    if not host:
        raise BlockedUrlError("URL is missing a host", url=text)
    host_n = _normalize_host(host)
    if hostname_looks_blocked(host_n):
        raise BlockedUrlError(f"blocked hostname: {host_n}", url=text)
    literal = parse_literal_ip(host_n)
    if literal is not None:
        return text
    addrs = await _resolve(host_n)
    if not addrs:
        raise FetchError(f"no addresses for {host_n}", url=text)
    for addr in addrs:
        parsed_ip = parse_literal_ip(addr)
        if parsed_ip is None or ip_is_blocked(parsed_ip):
            raise BlockedUrlError(f"blocked address {addr} for {host_n}", url=text)
    return text


async def _resolve(hostname: str) -> Sequence[str]:
    import asyncio

    try:
        return await asyncio.to_thread(lookup_host, hostname)
    except OSError as exc:
        raise FetchError(f"DNS lookup failed for {hostname}", url=hostname) from exc


def _normalize_host(hostname: str) -> str:
    host = hostname.strip().rstrip(".").lower()
    if not host:
        return ""
    try:
        return host.encode("idna").decode("ascii")
    except UnicodeError:
        return host
