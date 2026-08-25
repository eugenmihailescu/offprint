"""Optional Playwright second fetcher. Import-guarded; CI never needs Chromium."""

from __future__ import annotations

import importlib.util
import logging
from typing import Any
from urllib.parse import urlparse

from offprint.errors import BlockedUrlError, FetchError, UsageError
from offprint.session import RunSession
from offprint.ssrf import assert_public_http_url

log = logging.getLogger("offprint.extract.browser")

GOTO_TIMEOUT_MS = 20_000
SETTLE_MS = 250
INSTALL_HINT = "Playwright extra is not installed; install offprint[browser]"
CHROMIUM_HINT = "Playwright Chromium is not installed (playwright install chromium)"

# In-page schemes that do not hit the network. Abort everything else non-http(s).
_LOCAL_SCHEMES = frozenset({"about", "data", "blob"})


def playwright_available() -> bool:
    return importlib.util.find_spec("playwright") is not None


def require_playwright() -> None:
    if not playwright_available():
        raise UsageError(INSTALL_HINT)


async def allow_playwright_url(url: str) -> bool:
    """True if Playwright should continue this request; False → abort."""
    scheme = (urlparse(url).scheme or "").lower()
    if scheme in _LOCAL_SCHEMES:
        return True
    try:
        await assert_public_http_url(url)
    except (BlockedUrlError, FetchError):
        return False
    return True


async def handle_route(route: Any) -> None:
    url = route.request.url
    if await allow_playwright_url(url):
        await route.continue_()
        return
    log.debug("playwright abort %s", url)
    await route.abort()


class BrowserHandle:
    """Owns the Playwright driver + Chromium so ``session.aclose()`` stops both."""

    def __init__(self, playwright: Any, browser: Any) -> None:
        self.playwright = playwright
        self.browser = browser

    async def new_context(self, **kwargs: Any) -> Any:
        return await self.browser.new_context(**kwargs)

    async def close(self) -> None:
        try:
            await self.browser.close()
        finally:
            await self.playwright.stop()


async def _start_playwright() -> Any:
    from playwright.async_api import async_playwright

    return await async_playwright().start()


async def ensure_browser(session: RunSession) -> BrowserHandle:
    """Launch Chromium once per session. Safe to call from concurrent workers."""
    require_playwright()
    existing = session.browser
    if isinstance(existing, BrowserHandle):
        return existing
    async with session.browser_lock:
        existing = session.browser
        if isinstance(existing, BrowserHandle):
            return existing
        pw = await _start_playwright()
        try:
            browser = await pw.chromium.launch(headless=True)
        except Exception as exc:
            try:
                await pw.stop()
            except Exception:
                pass
            msg = str(exc).lower()
            if "executable" in msg or "playwright install" in msg:
                raise UsageError(CHROMIUM_HINT) from exc
            raise FetchError(str(exc) or "failed to launch Chromium") from exc
        handle = BrowserHandle(pw, browser)
        session.browser = handle
        return handle


async def render_html(
    url: str,
    session: RunSession,
    *,
    timeout_ms: int = GOTO_TIMEOUT_MS,
    user_agent: str | None = None,
) -> str:
    """Navigate ``url`` in a fresh context. Every request goes through SSRF."""
    handle = await ensure_browser(session)
    ua = user_agent or session.client.user_agent
    context = await handle.new_context(accept_downloads=False, user_agent=ua)
    try:
        page = await context.new_page()
        await page.route("**/*", handle_route)
        try:
            await page.goto(url, wait_until="load", timeout=timeout_ms)
        except TimeoutError as exc:
            raise FetchError("browser navigation timeout", url=url) from exc
        except Exception as exc:
            if type(exc).__name__ == "TimeoutError" or "Timeout" in type(exc).__name__:
                raise FetchError("browser navigation timeout", url=url) from exc
            raise FetchError(str(exc) or "browser navigation failed", url=url) from exc
        if SETTLE_MS > 0:
            await page.wait_for_timeout(SETTLE_MS)
        return await page.content()
    finally:
        await context.close()
