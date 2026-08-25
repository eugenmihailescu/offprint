"""SSRF host/IP policy. DNS is mocked; no live network."""

from __future__ import annotations

import ipaddress

import pytest

from offprint.errors import BlockedUrlError, FetchError
from offprint.ssrf import (
    assert_public_http_url,
    hostname_looks_blocked,
    ip_is_blocked,
    parse_literal_ip,
)


@pytest.mark.parametrize(
    "host",
    [
        "localhost",
        "localhost.",
        "metadata",
        "intranet",
        "foo.local",
        "foo.lan",
        "foo.internal",
        "kubernetes.default",
        "kubernetes.default.svc",
        "instance-data",
        "metadata.google.internal",
    ],
)
def test_hostname_blocked(host: str) -> None:
    assert hostname_looks_blocked(host)


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/",
        "http://user@169.254.169.254/",
        "http://user:pass@example.com/",
        "http://127.0.0.1/",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/",
        "http://2130706433/",
        "http://0177.0.0.1/",
        "http://[64:ff9b::7f00:1]/",
    ],
)
@pytest.mark.asyncio
async def test_assert_blocks(url: str, public_dns: None) -> None:
    with pytest.raises(BlockedUrlError) as exc:
        await assert_public_http_url(url)
    assert exc.value.code == "ssrf_blocked"


@pytest.mark.asyncio
async def test_public_url_allowed(public_dns: None) -> None:
    assert await assert_public_http_url("https://example.com/post") == "https://example.com/post"


@pytest.mark.asyncio
async def test_dns_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(hostname: str) -> list[str]:
        raise OSError("nxdomain")

    monkeypatch.setattr("offprint.ssrf.lookup_host", boom)
    with pytest.raises(FetchError) as exc:
        await assert_public_http_url("https://no-such-host.invalid/")
    assert exc.value.code == "network"


@pytest.mark.asyncio
async def test_resolved_private_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("offprint.ssrf.lookup_host", lambda host: ["127.0.0.1"])
    with pytest.raises(BlockedUrlError):
        await assert_public_http_url("https://evil.example/")


def test_decimal_and_nat64_parse() -> None:
    assert parse_literal_ip("2130706433") == ipaddress.IPv4Address("127.0.0.1")
    assert parse_literal_ip("0177.0.0.1") == ipaddress.IPv4Address("127.0.0.1")
    nat = parse_literal_ip("64:ff9b::7f00:1")
    assert nat is not None
    assert ip_is_blocked(nat)


def test_public_literal_ip_not_blocked() -> None:
    assert not hostname_looks_blocked("8.8.8.8")
    assert not ip_is_blocked(ipaddress.IPv4Address("8.8.8.8"))
