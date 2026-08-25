"""Feed item overlay for a URL (site mode injects the index)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from offprint.urls import canonical_key


@dataclass(frozen=True)
class FeedItem:
    link: str
    guid: str | None = None
    title: str | None = None
    published: str | None = None
    updated: str | None = None
    author: str | None = None
    tags: tuple[str, ...] = ()
    content_html: str | None = None
    summary: str | None = None
    categories: tuple[str, ...] = ()


def lookup_feed_item(
    url: str,
    index: Mapping[str, FeedItem] | None,
    extra_urls: tuple[str, ...] = (),
) -> FeedItem | None:
    if not index:
        return None
    keys = [url]
    keys.extend(extra_urls)
    seen: set[str] = set()
    for candidate in keys:
        try:
            key = canonical_key(candidate)
        except Exception:
            continue
        if key in seen:
            continue
        seen.add(key)
        item = index.get(key)
        if item is not None:
            return item
    return None
