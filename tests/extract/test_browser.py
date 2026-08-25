"""Playwright fallback. Default CI monkeypatches render_html; no Chromium required."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from offprint.errors import FetchError, NotArticleError, UsageError
from offprint.extract.browser import (
    INSTALL_HINT,
    BrowserHandle,
    allow_playwright_url,
    ensure_browser,
    handle_route,
    require_playwright,
)
from offprint.pipeline import ExtractOptions, extract_url_async
from offprint.session import open_session
from offprint.site import SiteOptions, extract_site_async

HTML = Path(__file__).resolve().parents[2] / "fixtures" / "html"
SPA = (HTML / "spa_empty.html").read_bytes()
ARTICLE_HTML = (HTML / "wordpress_entry_content.html").read_text(encoding="utf-8")


class _FakeRequest:
    def __init__(self, url: str) -> None:
        self.url = url


class _FakeRoute:
    def __init__(self, url: str) -> None:
        self.request = _FakeRequest(url)
        self.aborted = False
        self.continued = False

    async def abort(self) -> None:
        self.aborted = True

    async def continue_(self) -> None:
        self.continued = True


def test_require_playwright_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("offprint.extract.browser.playwright_available", lambda: False)
    with pytest.raises(UsageError, match="install offprint\\[browser\\]"):
        require_playwright()
    assert "offprint[browser]" in INSTALL_HINT


def test_capped_concurrency_browser_defaults(tmp_path: Path) -> None:
    out = tmp_path / "c.jsonl"
    on = SiteOptions(origin="https://example.com", out_path=out, browser=True)
    assert on.capped_concurrency() == 2
    capped = SiteOptions(origin="https://example.com", out_path=out, browser=True, concurrency=8)
    assert capped.capped_concurrency() == 4
    explicit = SiteOptions(origin="https://example.com", out_path=out, browser=True, concurrency=4)
    assert explicit.capped_concurrency() == 4
    auto = SiteOptions(origin="https://example.com", out_path=out, browser=None)
    assert auto.capped_concurrency() == 4


@pytest.mark.asyncio
async def test_allow_playwright_url_ssrf(public_dns: None) -> None:
    assert await allow_playwright_url("https://example.com/app.css") is True
    assert await allow_playwright_url("about:blank") is True
    assert await allow_playwright_url("data:text/html,hi") is True
    assert await allow_playwright_url("blob:https://example.com/1") is True
    assert await allow_playwright_url("http://127.0.0.1/") is False
    assert await allow_playwright_url("http://[::1]/") is False
    assert await allow_playwright_url("file:///etc/passwd") is False
    assert await allow_playwright_url("javascript:alert(1)") is False


@pytest.mark.asyncio
async def test_handle_route_aborts_private(public_dns: None) -> None:
    blocked = _FakeRoute("http://127.0.0.1/secret")
    await handle_route(blocked)
    assert blocked.aborted is True
    assert blocked.continued is False
    ok = _FakeRoute("https://cdn.example.com/app.js")
    await handle_route(ok)
    assert ok.continued is True
    assert ok.aborted is False


async def _fake_render(url: str, session: Any, **kwargs: Any) -> str:
    return ARTICLE_HTML


@pytest.mark.asyncio
@respx.mock
async def test_browser_fallback_monkeypatch(
    public_dns: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("offprint.extract.browser.playwright_available", lambda: True)
    monkeypatch.setattr("offprint.extract.browser.render_html", _fake_render)
    respx.get("https://example.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://example.com/spa").mock(
        return_value=httpx.Response(200, content=SPA, headers={"Content-Type": "text/html"})
    )
    art = await extract_url_async(
        "https://example.com/spa",
        ExtractOptions(browser=True, ignore_robots=True),
    )
    assert art.text
    assert "browser" in art.provenance.methodChain
    assert art.provenance.method == "html-article"


@pytest.mark.asyncio
@respx.mock
async def test_auto_fallback_monkeypatch(public_dns: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("offprint.extract.browser.playwright_available", lambda: True)
    monkeypatch.setattr("offprint.extract.browser.render_html", _fake_render)
    respx.get("https://example.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://example.com/spa").mock(
        return_value=httpx.Response(200, content=SPA, headers={"Content-Type": "text/html"})
    )
    art = await extract_url_async(
        "https://example.com/spa",
        ExtractOptions(browser=None, ignore_robots=True),
    )
    assert "browser" in art.provenance.methodChain


@pytest.mark.asyncio
@respx.mock
async def test_no_browser_skips_render(public_dns: None, monkeypatch: pytest.MonkeyPatch) -> None:
    async def boom(*args: Any, **kwargs: Any) -> str:
        raise AssertionError("render_html must not run")

    monkeypatch.setattr("offprint.extract.browser.playwright_available", lambda: True)
    monkeypatch.setattr("offprint.extract.browser.render_html", boom)
    respx.get("https://example.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://example.com/spa").mock(
        return_value=httpx.Response(200, content=SPA, headers={"Content-Type": "text/html"})
    )
    with pytest.raises(NotArticleError):
        await extract_url_async(
            "https://example.com/spa",
            ExtractOptions(browser=False, ignore_robots=True),
        )


@pytest.mark.asyncio
@respx.mock
async def test_auto_missing_extra_is_not_article(
    public_dns: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("offprint.extract.browser.playwright_available", lambda: False)
    respx.get("https://example.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://example.com/spa").mock(
        return_value=httpx.Response(200, content=SPA, headers={"Content-Type": "text/html"})
    )
    with pytest.raises(NotArticleError):
        await extract_url_async(
            "https://example.com/spa",
            ExtractOptions(browser=None, ignore_robots=True),
        )


@pytest.mark.asyncio
@respx.mock
async def test_force_browser_missing_extra_usage(
    public_dns: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("offprint.extract.browser.playwright_available", lambda: False)
    with pytest.raises(UsageError, match="install offprint\\[browser\\]"):
        await extract_url_async(
            "https://example.com/spa",
            ExtractOptions(browser=True, ignore_robots=True),
        )


@pytest.mark.asyncio
@respx.mock
async def test_force_browser_timeout_is_fetch_error(
    public_dns: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def timeout(*args: Any, **kwargs: Any) -> str:
        raise FetchError("browser navigation timeout", url=args[0] if args else None)

    monkeypatch.setattr("offprint.extract.browser.playwright_available", lambda: True)
    monkeypatch.setattr("offprint.extract.browser.render_html", timeout)
    respx.get("https://example.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://example.com/spa").mock(
        return_value=httpx.Response(200, content=SPA, headers={"Content-Type": "text/html"})
    )
    with pytest.raises(FetchError, match="timeout"):
        await extract_url_async(
            "https://example.com/spa",
            ExtractOptions(browser=True, ignore_robots=True),
        )


@pytest.mark.asyncio
@respx.mock
async def test_successful_overlay_does_not_render(
    public_dns: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def boom(*args: Any, **kwargs: Any) -> str:
        raise AssertionError("render_html must not run")

    monkeypatch.setattr("offprint.extract.browser.playwright_available", lambda: True)
    monkeypatch.setattr("offprint.extract.browser.render_html", boom)
    body = (HTML / "wordpress_entry_content.html").read_bytes()
    respx.get("https://example.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://example.com/p/fm").mock(
        return_value=httpx.Response(200, content=body, headers={"Content-Type": "text/html"})
    )
    art = await extract_url_async(
        "https://example.com/p/fm",
        ExtractOptions(browser=True, ignore_robots=True),
    )
    assert art.provenance.method == "html-article"
    assert "browser" not in art.provenance.methodChain


@pytest.mark.asyncio
async def test_ensure_browser_reuses_handle(monkeypatch: pytest.MonkeyPatch) -> None:
    starts = {"n": 0}

    class FakeChromium:
        async def launch(self, headless: bool = True) -> Any:
            return FakeBrowser()

    class FakePlaywright:
        chromium = FakeChromium()

        async def stop(self) -> None:
            starts["stopped"] = starts.get("stopped", 0) + 1

    class FakeBrowser:
        async def close(self) -> None:
            starts["closed"] = starts.get("closed", 0) + 1

        async def new_context(self, **kwargs: Any) -> Any:
            raise AssertionError("unused")

    async def fake_start() -> FakePlaywright:
        starts["n"] += 1
        return FakePlaywright()

    monkeypatch.setattr("offprint.extract.browser.playwright_available", lambda: True)
    monkeypatch.setattr("offprint.extract.browser._start_playwright", fake_start)
    session = await open_session(ignore_robots=True)
    try:
        first = await ensure_browser(session)
        second = await ensure_browser(session)
        assert first is second
        assert starts["n"] == 1
        assert isinstance(session.browser, BrowserHandle)
    finally:
        await session.aclose()
    assert starts.get("closed") == 1
    assert starts.get("stopped") == 1
    assert session.browser is None


@pytest.mark.asyncio
@respx.mock
async def test_extract_site_browser_fallback(
    public_dns: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    launched = {"n": 0}

    class Dummy:
        async def close(self) -> None:
            pass

    async def fake_ensure(session: Any) -> Any:
        launched["n"] += 1
        if session.browser is None:
            session.browser = Dummy()
        return session.browser

    monkeypatch.setattr("offprint.extract.browser.playwright_available", lambda: True)
    monkeypatch.setattr("offprint.site.job.ensure_browser", fake_ensure)
    monkeypatch.setattr("offprint.extract.browser.render_html", _fake_render)
    respx.get("https://example.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://example.com/spa-a").mock(
        return_value=httpx.Response(200, content=SPA, headers={"Content-Type": "text/html"})
    )
    respx.get("https://example.com/spa-b").mock(
        return_value=httpx.Response(200, content=SPA, headers={"Content-Type": "text/html"})
    )
    urls = tmp_path / "urls.txt"
    urls.write_text("https://example.com/spa-a\nhttps://example.com/spa-b\n", encoding="utf-8")
    out = tmp_path / "corpus.jsonl"
    manifest = await extract_site_async(
        SiteOptions(
            origin="https://example.com",
            out_path=out,
            urls_file=urls,
            delay=0,
            concurrency=2,
            ignore_robots=True,
            no_crawl=True,
            overwrite=True,
            browser=True,
        )
    )
    assert launched["n"] == 1
    assert manifest.stats.extracted == 2
    assert manifest.config.browser == "on"
    assert manifest.config.concurrency == 2
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert all('"browser"' in line for line in lines)


@pytest.mark.asyncio
@respx.mock
async def test_auto_browser_timeout_is_not_article(
    public_dns: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def timeout(*args: Any, **kwargs: Any) -> str:
        raise FetchError("browser navigation timeout", url="https://example.com/spa")

    monkeypatch.setattr("offprint.extract.browser.playwright_available", lambda: True)
    monkeypatch.setattr("offprint.extract.browser.render_html", timeout)
    respx.get("https://example.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://example.com/spa").mock(
        return_value=httpx.Response(200, content=SPA, headers={"Content-Type": "text/html"})
    )
    with pytest.raises(NotArticleError):
        await extract_url_async(
            "https://example.com/spa",
            ExtractOptions(browser=None, ignore_robots=True),
        )


@pytest.mark.live
@pytest.mark.asyncio
async def test_chromium_render_optional() -> None:
    if os.environ.get("OFFPRINT_LIVE") != "1":
        pytest.skip("set OFFPRINT_LIVE=1 to run Chromium")
    from offprint.extract.browser import playwright_available, render_html

    if not playwright_available():
        pytest.skip("playwright extra not installed")
    session = await open_session(ignore_robots=True)
    try:
        try:
            html = await render_html("https://example.com/", session)
        except UsageError as exc:
            pytest.skip(str(exc))
        assert "<html" in html.lower()
    finally:
        await session.aclose()
