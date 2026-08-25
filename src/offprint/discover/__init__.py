"""Discover article URLs from sitemaps, feeds, URL lists, and last-resort crawl."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

from offprint.constants import DEFAULT_MAX_URLS
from offprint.discover.classify import should_queue
from offprint.discover.crawl import crawl_home
from offprint.discover.feeds import parse_feed
from offprint.discover.sitemap import walk_sitemaps
from offprint.errors import HttpError, OffprintError, UsageError
from offprint.extract.feeds_match import FeedItem
from offprint.fetch import FetchClient, decode_body
from offprint.session import RunSession
from offprint.urls import canonical_key, parse_origin, same_site_family, www_apex_twin

log = logging.getLogger("offprint.discover")

WELL_KNOWN_SITEMAPS = (
    "/sitemap.xml",
    "/sitemap_index.xml",
    "/wp-sitemap.xml",
    "/sitemap.xml.gz",
    "/sitemap_index.xml.gz",
)
WELL_KNOWN_FEEDS = (
    "/feed",
    "/feed/",
    "/rss",
    "/rss.xml",
    "/atom.xml",
    "/index.xml",
    "/feed.xml",
    "/feeds/posts/default?alt=rss",
)


@dataclass(frozen=True)
class SkippedUrl:
    url: str
    code: str


@dataclass(frozen=True)
class Discovery:
    origin: str
    urls: tuple[str, ...]
    aliases: Mapping[str, tuple[str, ...]]
    feed_index: Mapping[str, FeedItem]
    skipped: tuple[SkippedUrl, ...]
    sitemaps_fetched: tuple[str, ...]
    feeds_fetched: tuple[str, ...]
    used_crawl: bool
    discovered_count: int
    feed_item_links: int = 0


def read_urls_file(path: Path, *, max_urls: int) -> list[str]:
    text = path.read_text(encoding="utf-8-sig")
    urls: list[str] = []
    for line in text.splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        urls.append(raw)
        if len(urls) >= max_urls:
            break
    return urls


async def _get(client: FetchClient, url: str):
    try:
        return await client.get(url)
    except HttpError:
        return None
    except OffprintError as exc:
        log.debug("discover fetch failed %s: %s", url, exc)
        return None


def _key(url: str) -> str | None:
    try:
        return canonical_key(url)
    except UsageError:
        return None


async def discover(
    origin: str,
    session: RunSession,
    *,
    max_urls: int = DEFAULT_MAX_URLS,
    include_paths: tuple[str, ...] = (),
    exclude_paths: tuple[str, ...] = (),
    no_crawl: bool = False,
    urls_file: Path | None = None,
    apply_deny_list: bool = True,
) -> Discovery:
    origin = parse_origin(origin)
    client = session.client
    await session.robots.allow(origin + "/", client.user_agent)

    if urls_file is not None:
        listed = read_urls_file(urls_file, max_urls=max_urls)
        return _classify(
            origin,
            listed,
            feed_index={},
            sitemaps_fetched=(),
            feeds_fetched=(),
            used_crawl=False,
            max_urls=max_urls,
            include_paths=include_paths,
            exclude_paths=exclude_paths,
            apply_deny_list=False,
        )

    sitemap_starts = [urljoin(origin + "/", p.lstrip("/")) for p in WELL_KNOWN_SITEMAPS]
    twin = www_apex_twin(origin)
    if twin:
        sitemap_starts.extend(urljoin(twin + "/", p.lstrip("/")) for p in WELL_KNOWN_SITEMAPS)
    sitemap_starts.extend(session.robots.sitemap_urls(origin + "/"))

    item_locs, fetched_sitemaps = await walk_sitemaps(client, sitemap_starts)

    feed_starts = [
        urljoin(origin + "/", p.lstrip("/")) if p.startswith("/") else urljoin(origin, p)
        for p in WELL_KNOWN_FEEDS
    ]
    if twin:
        feed_starts.extend(
            urljoin(twin + "/", p.lstrip("/")) if p.startswith("/") else urljoin(twin, p)
            for p in WELL_KNOWN_FEEDS
        )
    home = await _get(client, origin + "/")
    if home is not None:
        html = decode_body(home.body, home.content_type)
        feed_starts.extend(_alternate_feeds(html, home.final_url or origin + "/"))

    feed_index: dict[str, FeedItem] = {}
    feed_links: list[str] = []
    feeds_fetched: list[str] = []
    seen_feeds: set[str] = set()
    for furl in feed_starts:
        if furl in seen_feeds:
            continue
        seen_feeds.add(furl)
        result = await _get(client, furl)
        if result is None:
            continue
        feeds_fetched.append(furl)
        for item in parse_feed(result.body, content_type=result.content_type):
            key = _key(item.link)
            if key:
                feed_index[key] = item
            if same_site_family(item.link, origin):
                feed_links.append(item.link)

    family_locs = [
        u
        for u in dict.fromkeys([*item_locs, *feed_links])
        if same_site_family(u, origin) and _key(u)
    ]
    disc = _classify(
        origin,
        family_locs,
        feed_index=feed_index,
        sitemaps_fetched=tuple(fetched_sitemaps),
        feeds_fetched=tuple(feeds_fetched),
        used_crawl=False,
        max_urls=max_urls,
        include_paths=include_paths,
        exclude_paths=exclude_paths,
        apply_deny_list=apply_deny_list,
        feed_item_links=len(feed_links),
    )
    if disc.urls or feed_links or no_crawl:
        return disc

    crawled, only_home_fetch = await crawl_home(
        client,
        origin,
        include_paths=include_paths,
        exclude_paths=exclude_paths,
    )
    family_locs = [
        u
        for u in dict.fromkeys([*family_locs, *crawled])
        if same_site_family(u, origin) and _key(u)
    ]
    return _classify(
        origin,
        family_locs,
        feed_index=feed_index,
        sitemaps_fetched=tuple(fetched_sitemaps),
        feeds_fetched=tuple(feeds_fetched),
        used_crawl=True,
        max_urls=max_urls,
        include_paths=include_paths,
        exclude_paths=exclude_paths,
        apply_deny_list=apply_deny_list,
        feed_item_links=len(feed_links),
        force_only_home=only_home_fetch,
    )


def _alternate_feeds(html: str, base: str) -> list[str]:
    from lxml import html as lhtml

    try:
        tree = lhtml.document_fromstring(html)
    except Exception:
        return []
    out: list[str] = []
    for link in tree.xpath("//link[@rel='alternate']"):
        typ = (link.get("type") or "").lower()
        href = link.get("href")
        if not href:
            continue
        if any(t in typ for t in ("rss+xml", "atom+xml", "feed+json")):
            out.append(urljoin(base, href))
    return out


def _classify(
    origin: str,
    locs: list[str],
    *,
    feed_index: Mapping[str, FeedItem],
    sitemaps_fetched: tuple[str, ...],
    feeds_fetched: tuple[str, ...],
    used_crawl: bool,
    max_urls: int,
    include_paths: tuple[str, ...],
    exclude_paths: tuple[str, ...],
    apply_deny_list: bool,
    feed_item_links: int = 0,
    force_only_home: bool = False,
) -> Discovery:
    keys = []
    for url in locs:
        k = _key(url)
        if k:
            keys.append(k)
    unique_keys = set(keys)
    home_key = _key(origin + "/")
    only_home = force_only_home or (unique_keys == {home_key} if home_key else False)

    queued: list[str] = []
    aliases: dict[str, list[str]] = {}
    skipped: list[SkippedUrl] = []
    seen_q: set[str] = set()
    for url in locs:
        key = _key(url)
        if not key:
            continue
        aliases.setdefault(key, [])
        if url not in aliases[key]:
            aliases[key].append(url)
        ok = should_queue(
            url,
            include_paths=include_paths,
            exclude_paths=exclude_paths,
            only_home=only_home,
            apply_deny_list=apply_deny_list,
        )
        if not ok:
            if len(skipped) < 50:
                skipped.append(SkippedUrl(url=url, code="classify"))
            continue
        if key in seen_q:
            continue
        if len(queued) >= max_urls:
            continue
        seen_q.add(key)
        queued.append(url)

    if not queued and unique_keys == {home_key} and home_key:
        home = origin.rstrip("/") + "/"
        if should_queue(
            home,
            include_paths=include_paths,
            exclude_paths=exclude_paths,
            only_home=True,
            apply_deny_list=apply_deny_list,
        ):
            queued = [home]

    return Discovery(
        origin=origin,
        urls=tuple(queued),
        aliases={k: tuple(v) for k, v in aliases.items()},
        feed_index=dict(feed_index),
        skipped=tuple(skipped),
        sitemaps_fetched=sitemaps_fetched,
        feeds_fetched=feeds_fetched,
        used_crawl=used_crawl,
        discovered_count=len(unique_keys),
        feed_item_links=feed_item_links,
    )
