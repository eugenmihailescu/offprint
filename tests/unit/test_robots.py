"""Robots.txt allow/deny and crawl-delay clamp. Offline via respx."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from offprint.constants import ROBOTS_DELAY_CLAMP_SEC
from offprint.errors import RobotsDeniedError
from offprint.fetch import FetchClient
from offprint.robots import RobotsCache

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "robots"


@pytest.fixture
async def client(public_dns: None):
    c = FetchClient()
    try:
        yield c
    finally:
        await c.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_deny_all(client: FetchClient) -> None:
    body = (FIXTURES / "deny_all.txt").read_text(encoding="utf-8")
    respx.get("https://example.com/robots.txt").mock(return_value=httpx.Response(200, text=body))
    cache = RobotsCache(client)
    assert await cache.allow("https://example.com/blog/post", client.user_agent) is False
    with pytest.raises(RobotsDeniedError):
        await cache.require("https://example.com/blog/post", client.user_agent)


@pytest.mark.asyncio
@respx.mock
async def test_allow_path(client: FetchClient) -> None:
    body = (FIXTURES / "allow_blog.txt").read_text(encoding="utf-8")
    respx.get("https://example.com/robots.txt").mock(return_value=httpx.Response(200, text=body))
    cache = RobotsCache(client)
    assert await cache.allow("https://example.com/blog/post", client.user_agent) is True
    assert await cache.allow("https://example.com/secret", client.user_agent) is False


@pytest.mark.asyncio
@respx.mock
async def test_missing_robots_allows(client: FetchClient) -> None:
    respx.get("https://example.com/robots.txt").mock(return_value=httpx.Response(404))
    cache = RobotsCache(client)
    assert await cache.allow("https://example.com/any", client.user_agent) is True


@pytest.mark.asyncio
@respx.mock
async def test_ignore_robots(client: FetchClient) -> None:
    body = (FIXTURES / "deny_all.txt").read_text(encoding="utf-8")
    respx.get("https://example.com/robots.txt").mock(return_value=httpx.Response(200, text=body))
    cache = RobotsCache(client, ignore=True)
    assert await cache.allow("https://example.com/nope", client.user_agent) is True
    assert cache.crawl_interval("https://example.com/", client.user_agent) == 0.0


@pytest.mark.asyncio
@respx.mock
async def test_crawl_delay_clamp(client: FetchClient) -> None:
    body = (FIXTURES / "crawl_delay.txt").read_text(encoding="utf-8")
    respx.get("https://example.com/robots.txt").mock(return_value=httpx.Response(200, text=body))
    cache = RobotsCache(client)
    await cache.allow("https://example.com/", client.user_agent)
    raw = cache.crawl_interval("https://example.com/", client.user_agent)
    assert raw >= 20
    assert cache.clamp_interval(raw) == ROBOTS_DELAY_CLAMP_SEC
