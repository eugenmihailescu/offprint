"""extract_url / extract_url_async — fetch, overlay, sanitize, emit Article."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from offprint.constants import (
    ARTICLE_HTML_MAX_CHARS,
    DEFAULT_CONNECT_TIMEOUT_SEC,
    DEFAULT_MAX_BYTES,
    DEFAULT_MAX_REDIRECTS,
    DEFAULT_MIN_TEXT_CHARS,
    DEFAULT_READ_TIMEOUT_SEC,
    EXCERPT_MAX_CHARS,
    TEXT_MAX_CHARS,
    TIMEOUT_HARD_CAP_SEC,
    TITLE_MAX_CHARS,
)
from offprint.dates import parse_datetime
from offprint.errors import FetchError, NotArticleError, SizeError, UsageError
from offprint.extract import browser as browser_mod
from offprint.extract.feeds_match import FeedItem, lookup_feed_item
from offprint.extract.media import catalog_media, enrich_media
from offprint.extract.overlay import OverlayResult, overlay
from offprint.extract.sanitize import html_to_text, sanitize
from offprint.fetch import FetchResult, decode_body
from offprint.model import Article, Provenance, TruncatedField
from offprint.session import RunSession, open_session
from offprint.urls import canonical_key, parse_origin

log = logging.getLogger("offprint.pipeline")


@dataclass(frozen=True)
class ExtractOptions:
    origin: str | None = None
    ignore_robots: bool = False
    timeout: float = DEFAULT_READ_TIMEOUT_SEC
    connect_timeout: float = DEFAULT_CONNECT_TIMEOUT_SEC
    max_bytes: int = DEFAULT_MAX_BYTES
    max_redirects: int = DEFAULT_MAX_REDIRECTS
    user_agent: str | None = None
    save_html_dir: Path | None = None
    browser: bool | None = None
    min_text_chars: int = DEFAULT_MIN_TEXT_CHARS
    probe_media: bool = False
    download_media_dir: Path | None = None
    feed_index: Mapping[str, FeedItem] | None = None
    session: RunSession | None = None


def extract_url(url: str, options: ExtractOptions | None = None) -> Article:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(extract_url_async(url, options))
    raise UsageError("use extract_url_async inside a running event loop")


async def extract_url_async(url: str, options: ExtractOptions | None = None) -> Article:
    opts = options or ExtractOptions()
    if opts.browser is True:
        browser_mod.require_playwright()
    own = opts.session is None
    session = opts.session or await open_session(
        ignore_robots=opts.ignore_robots,
        timeout=opts.timeout,
        connect_timeout=opts.connect_timeout,
        max_bytes=opts.max_bytes,
        max_redirects=opts.max_redirects,
        user_agent=opts.user_agent,
    )

    async def hop_ok(hop: str) -> None:
        await session.robots.require(hop, session.client.user_agent)

    try:
        fetched = await session.client.get(url, hop_ok=hop_ok)
        html = decode_body(fetched.body, fetched.content_type)
        return await _article_from_fetch_async(html, fetched, opts, session)
    finally:
        if own:
            await session.aclose()


def _lookup_feed(fetched: FetchResult, options: ExtractOptions) -> FeedItem | None:
    return lookup_feed_item(
        fetched.requested_url,
        options.feed_index,
        extra_urls=(fetched.final_url, *fetched.redirects),
    )


def _overlay_html(html: str, fetched: FetchResult, options: ExtractOptions) -> OverlayResult | None:
    return overlay(
        html,
        url=fetched.final_url,
        feed=_lookup_feed(fetched, options),
        min_text_chars=options.min_text_chars,
    )


async def _maybe_render(url: str, session: RunSession, options: ExtractOptions) -> str | None:
    if options.browser is False:
        return None
    if not browser_mod.playwright_available():
        if options.browser is True:
            browser_mod.require_playwright()
        return None
    timeout_ms = int(min(max(options.timeout, 0.001), TIMEOUT_HARD_CAP_SEC) * 1000)
    try:
        return await browser_mod.render_html(
            url,
            session,
            timeout_ms=timeout_ms,
            user_agent=session.client.user_agent,
        )
    except UsageError:
        if options.browser is True:
            raise
        log.warning("playwright extra/chromium unavailable; skipping browser fallback")
        return None
    except FetchError:
        if options.browser is True:
            raise
        log.warning("playwright fallback failed for %s", url)
        return None


async def _article_from_fetch_async(
    html: str,
    fetched: FetchResult,
    options: ExtractOptions,
    session: RunSession,
) -> Article:
    result = _overlay_html(html, fetched, options)
    if result is None and options.browser is not False:
        rendered = await _maybe_render(fetched.final_url, session, options)
        if rendered is not None:
            result = _overlay_html(rendered, fetched, options)
            if result is not None:
                result.method_chain = list(dict.fromkeys([*result.method_chain, "browser"]))
    if result is None:
        raise NotArticleError("page is not an article", url=fetched.final_url)
    article = _emit_article(result, fetched, options)
    if options.probe_media or options.download_media_dir is not None:
        await enrich_media(
            article.media,
            session.client,
            probe=options.probe_media,
            download_dir=options.download_media_dir,
        )
    return article


def article_from_fetch(html: str, fetched: FetchResult, options: ExtractOptions) -> Article:
    """Sync overlay path used by quality tests. Does not launch Playwright."""
    result = _overlay_html(html, fetched, options)
    if result is None:
        raise NotArticleError("page is not an article", url=fetched.final_url)
    return _emit_article(result, fetched, options)


def _emit_article(result: OverlayResult, fetched: FetchResult, options: ExtractOptions) -> Article:
    if len(result.html) > ARTICLE_HTML_MAX_CHARS:
        raise SizeError("article html exceeds cap", url=fetched.final_url)

    clean = sanitize(result.html, base_url=fetched.final_url)
    text = html_to_text(clean)
    truncated: list[TruncatedField] = []
    title = _clip(result.meta.title, TITLE_MAX_CHARS, "title", truncated)
    excerpt = _clip(result.meta.excerpt, EXCERPT_MAX_CHARS, "excerpt", truncated)
    text = _clip(text, TEXT_MAX_CHARS, "text", truncated) or ""

    origin = options.origin or parse_origin(fetched.requested_url)
    canonical = _canonical(result.meta.canonical, fetched)
    discovered = _discovered(fetched, canonical)

    raw_sha = hashlib.sha256(fetched.body).hexdigest()
    raw_path = None
    if options.save_html_dir is not None:
        options.save_html_dir.mkdir(parents=True, exist_ok=True)
        dest = options.save_html_dir / f"{raw_sha}.html"
        dest.write_bytes(fetched.body)
        raw_path = str(dest)

    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as pkg_version

    try:
        version = pkg_version("offprint")
    except PackageNotFoundError:
        version = "0.0.0"

    media = catalog_media(clean, extra=result.meta.images, base_url=fetched.final_url)
    authors = result.meta.author_names[:12]
    tags = result.meta.tags[:64]
    categories = result.meta.categories[:32]
    if len(result.meta.author_names) > 12:
        truncated.append("authorNames")
    if len(result.meta.tags) > 64:
        truncated.append("tags")
    if len(result.meta.categories) > 32:
        truncated.append("categories")

    return Article(
        origin=origin,
        canonicalUrl=canonical,
        discoveredUrls=discovered[:50],
        title=title or "",
        publishedAt=parse_datetime(result.meta.published_at),
        updatedAt=parse_datetime(result.meta.updated_at),
        lang=result.meta.lang,
        authorNames=authors,
        tags=tags,
        categories=categories,
        excerpt=excerpt,
        html=clean,
        text=text,
        media=media,
        provenance=Provenance(
            method=result.method,
            methodChain=result.method_chain,
            fetchedAt=fetched.fetched_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            finalUrl=fetched.final_url,
            httpStatus=fetched.status,
            contentType=fetched.content_type,
            bytes=len(fetched.body),
            redirects=list(fetched.redirects),
            extractorVersion=f"offprint/{version}",
            rawHtmlSha256=raw_sha,
            rawHtmlPath=raw_path,
            robotsIgnored=options.ignore_robots,
            truncated=truncated,
        ),
    )


def _clip(
    value: str | None,
    limit: int,
    field: TruncatedField,
    truncated: list[TruncatedField],
) -> str | None:
    if value is None:
        return None
    if len(value) <= limit:
        return value
    truncated.append(field)
    return value[:limit]


def _canonical(hint: str | None, fetched: FetchResult) -> str:
    if hint:
        from urllib.parse import urljoin

        abs_hint = urljoin(fetched.final_url, hint)
        try:
            canonical_key(abs_hint)
            return abs_hint
        except Exception:
            pass
    return fetched.final_url


def _discovered(fetched: FetchResult, canonical: str) -> list[str]:
    urls = [fetched.requested_url, fetched.final_url, canonical, *fetched.redirects]
    out: list[str] = []
    seen: set[str] = set()
    for item in urls:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out
