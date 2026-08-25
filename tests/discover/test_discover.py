from pathlib import Path

import httpx
import pytest
import respx

from offprint.discover import discover
from offprint.session import open_session
from offprint.urls import same_site_family

FIX = Path(__file__).resolve().parents[2] / "fixtures"


@pytest.mark.asyncio
@respx.mock
async def test_www_child_sitemap(public_dns: None) -> None:
    index = (FIX / "sitemaps/index_www.xml").read_bytes()
    child = (FIX / "sitemaps/sitemap-posts.xml").read_bytes()
    respx.get("https://example.com/sitemap.xml").mock(
        return_value=httpx.Response(200, content=index, headers={"Content-Type": "application/xml"})
    )
    respx.get("https://www.example.com/sitemap-posts.xml").mock(
        return_value=httpx.Response(200, content=child, headers={"Content-Type": "application/xml"})
    )
    respx.route().mock(return_value=httpx.Response(404))
    session = await open_session(ignore_robots=True)
    try:
        disc = await discover("https://example.com", session, no_crawl=True)
    finally:
        await session.aclose()
    assert any(same_site_family(u, "https://example.com") for u in disc.urls)
    assert any("from-www" in u for u in disc.urls)


@pytest.mark.asyncio
@respx.mock
async def test_taxonomy_does_not_starve_posts(public_dns: None) -> None:
    body = (FIX / "sitemaps/taxonomy.xml").read_bytes()
    respx.get("https://example.com/sitemap.xml").mock(
        return_value=httpx.Response(200, content=body, headers={"Content-Type": "application/xml"})
    )
    respx.route().mock(return_value=httpx.Response(404))
    session = await open_session(ignore_robots=True)
    try:
        disc = await discover("https://example.com", session, no_crawl=True, max_urls=50)
    finally:
        await session.aclose()
    assert "https://example.com/blog/real-post" in disc.urls
    assert not any("/category/" in u for u in disc.urls)
