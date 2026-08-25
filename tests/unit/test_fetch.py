"""Fetch client: byte cap, cookies, redirects, HTTP errors. Offline via respx."""

from __future__ import annotations

import gzip

import httpx
import pytest
import respx

from offprint.errors import BlockedUrlError, HttpError, SizeError
from offprint.fetch import FetchClient, NullCookies, decode_body
from offprint.session import open_session


@pytest.mark.asyncio
@respx.mock
async def test_get_ok(public_dns: None) -> None:
    respx.get("https://example.com/p").mock(
        return_value=httpx.Response(200, content=b"hello", headers={"Content-Type": "text/html"})
    )
    client = FetchClient()
    try:
        result = await client.get("https://example.com/p")
    finally:
        await client.aclose()
    assert result.status == 200
    assert result.body == b"hello"
    assert result.final_url == "https://example.com/p"
    assert result.redirects == ()
    assert result.fetched_at.tzinfo is not None


@pytest.mark.asyncio
@respx.mock
async def test_no_cookie_jar(public_dns: None) -> None:
    respx.get("https://example.com/a").mock(
        return_value=httpx.Response(
            200,
            content=b"a",
            headers={"Set-Cookie": "sid=1; Path=/"},
        )
    )
    respx.get("https://example.com/b").mock(return_value=httpx.Response(200, content=b"b"))
    client = FetchClient()
    try:
        await client.get("https://example.com/a")
        await client.get("https://example.com/b")
    finally:
        await client.aclose()
    second = respx.calls[1].request
    assert "cookie" not in {k.lower() for k in second.headers.keys()}
    assert "sid" not in second.headers.get("Cookie", "")


@pytest.mark.asyncio
@respx.mock
async def test_redirect_to_private_blocked(public_dns: None) -> None:
    respx.get("https://example.com/go").mock(
        return_value=httpx.Response(302, headers={"Location": "http://127.0.0.1/secret"})
    )
    client = FetchClient()
    try:
        with pytest.raises(BlockedUrlError):
            await client.get("https://example.com/go")
    finally:
        await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_http_404(public_dns: None) -> None:
    respx.get("https://example.com/missing").mock(return_value=httpx.Response(404, content=b"no"))
    client = FetchClient()
    try:
        with pytest.raises(HttpError) as exc:
            await client.get("https://example.com/missing")
        assert exc.value.code == "http_4xx"
        assert exc.value.exit_code == 5
    finally:
        await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_gzip_bomb(public_dns: None) -> None:
    payload = gzip.compress(b"\x00" * (2 * 1024 * 1024))
    respx.get("https://example.com/bomb").mock(
        return_value=httpx.Response(
            200,
            content=payload,
            headers={"Content-Encoding": "gzip", "Content-Type": "text/html"},
        )
    )
    client = FetchClient(max_bytes=1024 * 1024)
    try:
        with pytest.raises(SizeError) as exc:
            await client.get("https://example.com/bomb")
        assert exc.value.code == "too_large"
    finally:
        await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_content_length_identity_early_abort(public_dns: None) -> None:
    respx.get("https://example.com/big").mock(
        return_value=httpx.Response(
            200,
            content=b"x",
            headers={"Content-Length": str(50 * 1024 * 1024), "Content-Type": "text/plain"},
        )
    )
    client = FetchClient(max_bytes=1024)
    try:
        with pytest.raises(SizeError):
            await client.get("https://example.com/big")
    finally:
        await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_redirect_chain(public_dns: None) -> None:
    respx.get("https://example.com/one").mock(
        return_value=httpx.Response(301, headers={"Location": "/two"})
    )
    respx.get("https://example.com/two").mock(return_value=httpx.Response(200, content=b"ok"))
    client = FetchClient()
    try:
        result = await client.get("https://example.com/one")
    finally:
        await client.aclose()
    assert result.body == b"ok"
    assert result.redirects == ("https://example.com/two",)
    assert result.final_url == "https://example.com/two"


def test_decode_body_charset() -> None:
    text = decode_body("café".encode("latin-1"), "text/html; charset=iso-8859-1")
    assert "caf" in text


def test_null_cookies_drop_writes() -> None:
    jar = NullCookies()
    jar.set("sid", "1")
    assert list(jar.keys()) == []


@pytest.mark.asyncio
@respx.mock
async def test_open_session(public_dns: None) -> None:
    respx.get("https://example.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://example.com/p").mock(return_value=httpx.Response(200, content=b"x"))
    session = await open_session()
    try:
        result = await session.client.get("https://example.com/p")
        assert result.body == b"x"
        assert await session.robots.allow("https://example.com/p", session.client.user_agent)
    finally:
        await session.aclose()
