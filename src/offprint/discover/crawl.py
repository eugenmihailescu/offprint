"""Last-resort homepage BFS when discovery queued nothing."""

from __future__ import annotations

import logging
from collections import deque
from urllib.parse import urljoin, urlparse

from lxml import html as lhtml

from offprint.constants import CRAWL_MAX_DEPTH, CRAWL_MAX_PAGES
from offprint.discover.classify import should_queue
from offprint.errors import HttpError, OffprintError
from offprint.fetch import FetchClient, decode_body
from offprint.urls import same_site_family

log = logging.getLogger("offprint.discover")


def hrefs_from_html(html: str, base: str) -> list[str]:
    try:
        tree = lhtml.document_fromstring(html)
    except Exception:
        return []
    out: list[str] = []
    for href in tree.xpath("//a/@href"):
        abs_url = urljoin(base, str(href).strip())
        if urlparse(abs_url).scheme in ("http", "https"):
            out.append(abs_url)
    return out


async def crawl_home(
    client: FetchClient,
    origin: str,
    *,
    include_paths: tuple[str, ...] = (),
    exclude_paths: tuple[str, ...] = (),
    max_pages: int = CRAWL_MAX_PAGES,
    max_depth: int = CRAWL_MAX_DEPTH,
) -> tuple[list[str], bool]:
    """Return (candidate URLs including possibly home, home_was_only_fetch)."""
    start = origin.rstrip("/") + "/"
    queue: deque[tuple[str, int]] = deque([(start, 0)])
    seen: set[str] = set()
    found: list[str] = []
    fetched_pages = 0
    fetched_only_home = True
    while queue and fetched_pages < max_pages:
        url, depth = queue.popleft()
        if url in seen or depth > max_depth:
            continue
        seen.add(url)
        try:
            result = await client.get(url)
        except HttpError:
            continue
        except OffprintError as exc:
            log.debug("crawl skip %s: %s", url, exc)
            continue
        fetched_pages += 1
        if urlparse(url).path not in ("", "/") or not same_site_family(url, origin):
            fetched_only_home = False
        html = decode_body(result.body, result.content_type)
        if depth == 0:
            found.append(result.final_url or url)
        for href in hrefs_from_html(html, result.final_url or url):
            if not same_site_family(href, origin):
                continue
            if should_queue(
                href,
                include_paths=include_paths,
                exclude_paths=exclude_paths,
                only_home=False,
            ):
                found.append(href)
            if depth + 1 <= max_depth and href not in seen:
                queue.append((href, depth + 1))
    only_home_fetch = fetched_pages == 1 and fetched_only_home
    return list(dict.fromkeys(found)), only_home_fetch
