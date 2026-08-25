"""extract_url_async against fixture HTML (respx, no live network)."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from offprint.pipeline import ExtractOptions, extract_url_async

HTML = Path(__file__).resolve().parents[2] / "fixtures" / "html"


@pytest.mark.asyncio
@respx.mock
async def test_extract_url_async_wordpress(public_dns: None) -> None:
    body = (HTML / "wordpress_entry_content.html").read_bytes()
    respx.get("https://example.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://example.com/p/fm").mock(
        return_value=httpx.Response(200, content=body, headers={"Content-Type": "text/html"})
    )
    art = await extract_url_async("https://example.com/p/fm", ExtractOptions())
    assert art.kind == "offprint-article"
    assert art.provenance.method == "html-article"
    assert art.origin == "https://example.com"
    assert art.html
    assert art.text
