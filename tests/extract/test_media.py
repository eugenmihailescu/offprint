"""Optional --probe-media / --download-media (SSRF, warnings, not article failures)."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx

from offprint.extract.media import catalog_media, guess_media_ext
from offprint.fetch import FetchResult
from offprint.pipeline import ExtractOptions, article_from_fetch, extract_url_async

HTML = Path(__file__).resolve().parents[2] / "fixtures" / "html"
JPG = b"\xff\xd8\xff\xd9" + b"jpeg-bytes"


def test_catalog_clips_long_alt() -> None:
    alt = "x" * 1500
    html = f'<img src="https://example.com/a.jpg" alt="{alt}">'
    items = catalog_media(html, extra=[], base_url="https://example.com/")
    assert len(items) == 1
    assert items[0].alt is not None
    assert len(items[0].alt) == 1000


def test_article_caps_media_at_500() -> None:
    imgs = "".join(f'<img src="/m/{i}.jpg" alt="shot">' for i in range(520))
    body = (
        "<html><body><div class='entry-content'><p>"
        + ("word " * 80)
        + f"</p>{imgs}</div></body></html>"
    )
    fetched = FetchResult(
        requested_url="https://example.com/grid",
        final_url="https://example.com/grid",
        status=200,
        content_type="text/html",
        body=body.encode("utf-8"),
        redirects=(),
        fetched_at=datetime(2026, 8, 25, 12, 0, tzinfo=UTC),
    )
    art = article_from_fetch(body, fetched, ExtractOptions())
    assert len(art.media) == 500
    assert "media" in art.provenance.truncated


def test_guess_media_ext() -> None:
    assert guess_media_ext("https://cdn.example/x.jpg?w=1", "image/png") == ".jpg"
    assert guess_media_ext("https://cdn.example/x", "image/png") == ".png"
    assert guess_media_ext("https://cdn.example/x.php", "image/jpeg") == ".jpg"
    assert guess_media_ext("https://cdn.example/x", None) == ".bin"


@pytest.mark.asyncio
@respx.mock
async def test_probe_media_head(public_dns: None) -> None:
    page = (HTML / "wordpress_entry_content.html").read_bytes()
    respx.get("https://example.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://example.com/p/fm").mock(
        return_value=httpx.Response(200, content=page, headers={"Content-Type": "text/html"})
    )
    respx.head("https://example.com/media/foo.jpg").mock(
        return_value=httpx.Response(
            200,
            headers={"Content-Type": "image/jpeg", "Content-Length": "1234"},
        )
    )
    respx.head("https://example.com/og.jpg").mock(
        return_value=httpx.Response(
            200,
            headers={"Content-Type": "image/jpeg", "Content-Length": "99"},
        )
    )
    art = await extract_url_async(
        "https://example.com/p/fm",
        ExtractOptions(ignore_robots=True, probe_media=True),
    )
    by_src = {m.src: m for m in art.media}
    foo = by_src["https://example.com/media/foo.jpg"]
    assert foo.mimeType == "image/jpeg"
    assert foo.byteSize == 1234


@pytest.mark.asyncio
@respx.mock
async def test_probe_media_range_fallback(public_dns: None) -> None:
    page = (HTML / "wordpress_entry_content.html").read_bytes()
    respx.get("https://example.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://example.com/p/fm").mock(
        return_value=httpx.Response(200, content=page, headers={"Content-Type": "text/html"})
    )
    respx.head("https://example.com/media/foo.jpg").mock(return_value=httpx.Response(405))
    respx.head("https://example.com/og.jpg").mock(return_value=httpx.Response(405))
    respx.get("https://example.com/media/foo.jpg").mock(
        return_value=httpx.Response(
            206,
            content=b"x",
            headers={
                "Content-Type": "image/jpeg",
                "Content-Range": "bytes 0-0/4321",
            },
        )
    )
    respx.get("https://example.com/og.jpg").mock(
        return_value=httpx.Response(
            206,
            content=b"y",
            headers={"Content-Type": "image/jpeg", "Content-Range": "bytes 0-0/10"},
        )
    )
    art = await extract_url_async(
        "https://example.com/p/fm",
        ExtractOptions(ignore_robots=True, probe_media=True),
    )
    foo = next(m for m in art.media if m.src.endswith("foo.jpg"))
    assert foo.byteSize == 4321
    assert foo.mimeType == "image/jpeg"


@pytest.mark.asyncio
@respx.mock
async def test_download_media_writes_sha(public_dns: None, tmp_path: Path) -> None:
    page = (HTML / "wordpress_entry_content.html").read_bytes()
    dest = tmp_path / "media"
    respx.get("https://example.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://example.com/p/fm").mock(
        return_value=httpx.Response(200, content=page, headers={"Content-Type": "text/html"})
    )
    respx.get("https://example.com/media/foo.jpg").mock(
        return_value=httpx.Response(200, content=JPG, headers={"Content-Type": "image/jpeg"})
    )
    respx.get("https://example.com/og.jpg").mock(
        return_value=httpx.Response(200, content=JPG, headers={"Content-Type": "image/jpeg"})
    )
    art = await extract_url_async(
        "https://example.com/p/fm",
        ExtractOptions(ignore_robots=True, download_media_dir=dest),
    )
    sha = hashlib.sha256(JPG).hexdigest()
    written = dest / f"{sha}.jpg"
    assert written.is_file()
    assert written.read_bytes() == JPG
    foo = next(m for m in art.media if m.src.endswith("foo.jpg"))
    assert foo.mimeType == "image/jpeg"
    assert foo.byteSize == len(JPG)


@pytest.mark.asyncio
@respx.mock
async def test_download_failure_does_not_fail_article(public_dns: None, tmp_path: Path) -> None:
    page = (HTML / "wordpress_entry_content.html").read_bytes()
    dest = tmp_path / "media"
    respx.get("https://example.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://example.com/p/fm").mock(
        return_value=httpx.Response(200, content=page, headers={"Content-Type": "text/html"})
    )
    respx.get("https://example.com/media/foo.jpg").mock(return_value=httpx.Response(404))
    respx.get("https://example.com/og.jpg").mock(return_value=httpx.Response(404))
    art = await extract_url_async(
        "https://example.com/p/fm",
        ExtractOptions(ignore_robots=True, download_media_dir=dest),
    )
    assert art.text
    assert list(dest.glob("*")) == []


@pytest.mark.asyncio
@respx.mock
async def test_download_ssrf_is_warning(public_dns: None, tmp_path: Path) -> None:
    body = (
        b"<!DOCTYPE html><html><body><div class='entry-content'>"
        b"<p>" + (b"word " * 80) + b"</p>"
        b"<img src='http://127.0.0.1/secret.jpg' alt='x'>"
        b"</div></body></html>"
    )
    dest = tmp_path / "media"
    respx.get("https://example.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://example.com/p/fm").mock(
        return_value=httpx.Response(200, content=body, headers={"Content-Type": "text/html"})
    )
    art = await extract_url_async(
        "https://example.com/p/fm",
        ExtractOptions(ignore_robots=True, download_media_dir=dest, probe_media=True),
    )
    assert art.text
    assert any("127.0.0.1" in m.src for m in art.media)
    assert list(dest.glob("*")) == []
    private = next(m for m in art.media if "127.0.0.1" in m.src)
    assert private.mimeType is None
    assert private.byteSize is None
