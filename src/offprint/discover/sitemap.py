"""Parse sitemap urlset / sitemapindex. XXE-safe. Optional gzip."""

from __future__ import annotations

import gzip
import logging
from collections.abc import Callable

from lxml import etree

from offprint.constants import MAX_SITEMAPS
from offprint.errors import SizeError
from offprint.fetch import FetchClient, FetchResult

log = logging.getLogger("offprint.discover")

_PARSER = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)


def maybe_gunzip(url: str, content_type: str | None, body: bytes) -> bytes:
    ctype = (content_type or "").lower()
    if body.startswith(b"\x1f\x8b") or url.endswith(".gz") or "gzip" in ctype:
        if body.startswith(b"\x1f\x8b"):
            return gzip.decompress(body)
    return body


def parse_sitemap_xml(body: bytes) -> tuple[str, list[str]]:
    """Return (\"index\"|\"urlset\", locs)."""
    try:
        root = etree.fromstring(body, parser=_PARSER)
    except etree.XMLSyntaxError as exc:
        log.debug("sitemap xml error: %s", exc)
        return ("urlset", [])
    name = etree.QName(root).localname.lower()
    locs = [str(t).strip() for t in root.xpath("//*[local-name()='loc']/text()") if str(t).strip()]
    if name == "sitemapindex":
        return ("index", locs)
    return ("urlset", locs)


async def fetch_sitemap(client: FetchClient, url: str) -> tuple[str, list[str]]:
    result: FetchResult = await client.get(url)
    body = maybe_gunzip(url, result.content_type, result.body)
    return parse_sitemap_xml(body)


async def walk_sitemaps(
    client: FetchClient,
    start_urls: list[str],
    *,
    on_progress: Callable[[int, int], None] | None = None,
) -> tuple[list[str], list[str]]:
    """Follow sitemapindex children (cap MAX_SITEMAPS). Returns (item_locs, fetched_urls)."""
    fetched: list[str] = []
    items: list[str] = []
    queue = list(dict.fromkeys(start_urls))
    seen: set[str] = set()
    while queue and len(fetched) < MAX_SITEMAPS:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        try:
            kind, locs = await fetch_sitemap(client, url)
        except SizeError:
            raise
        except Exception as exc:
            log.debug("sitemap fetch failed %s: %s", url, exc)
            continue
        fetched.append(url)
        if kind == "index":
            for child in locs:
                if child not in seen and len(fetched) + len(queue) < MAX_SITEMAPS:
                    queue.append(child)
                elif child not in seen:
                    queue.append(child)
                    if len(fetched) >= MAX_SITEMAPS:
                        break
        else:
            items.extend(locs)
        if on_progress is not None:
            on_progress(len(fetched), len(items))
    return items, fetched
