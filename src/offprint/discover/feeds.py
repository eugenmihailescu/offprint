"""RSS/Atom via feedparser (bytes only) and JSON Feed via stdlib json."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from time import struct_time
from typing import Any

import feedparser

from offprint.dates import parse_datetime
from offprint.extract.feeds_match import FeedItem

log = logging.getLogger("offprint.discover")


def _tag_terms(tags: Any) -> tuple[str, ...]:
    out: list[str] = []
    for tag in tags or []:
        if isinstance(tag, dict):
            term = tag.get("term") or tag.get("label")
        else:
            term = getattr(tag, "term", None) or getattr(tag, "label", None)
        if term:
            out.append(str(term))
    return tuple(out)


def _from_struct(st: struct_time | None) -> str | None:
    if not st:
        return None
    try:
        return datetime(*st[:6], tzinfo=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError, OverflowError):
        return None


def _entry_html(entry: Any) -> str | None:
    for block in entry.get("content") or []:
        val = block.get("value") if isinstance(block, dict) else getattr(block, "value", None)
        if val:
            return str(val)
    encoded = entry.get("content_encoded")
    if encoded:
        return str(encoded)
    return None


def _is_json_feed(content_type: str | None, body: bytes) -> dict[str, Any] | None:
    ctype = (content_type or "").lower()
    if "json" not in ctype and not body.lstrip().startswith(b"{"):
        return None
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    version = str(data.get("version") or "")
    if version.startswith("https://jsonfeed.org/version/"):
        return data
    if "items" in data and "feed_url" in data:
        return data
    return None


def parse_feed(body: bytes, *, content_type: str | None = None) -> list[FeedItem]:
    jf = _is_json_feed(content_type, body)
    if jf is not None:
        return _parse_json_feed(jf)
    parsed = feedparser.parse(
        body,
        response_headers={"content-type": content_type or "application/xml"},
    )
    items: list[FeedItem] = []
    for entry in parsed.entries:
        link = str(entry.get("link") or "")
        guid = str(entry.get("id") or "") or None
        if not link and guid and guid.startswith("http"):
            link = guid
        if not link:
            continue
        html = _entry_html(entry)
        summary = entry.get("summary")
        authors = entry.get("author") or entry.get("dc_creator")
        tags = _tag_terms(entry.get("tags"))
        published = _from_struct(entry.get("published_parsed")) or parse_datetime(
            entry.get("published")
        )
        updated = _from_struct(entry.get("updated_parsed")) or parse_datetime(entry.get("updated"))
        items.append(
            FeedItem(
                link=link,
                guid=guid,
                title=entry.get("title"),
                published=published,
                updated=updated,
                author=str(authors) if authors else None,
                tags=tags,
                content_html=html,
                summary=str(summary) if summary else None,
            )
        )
    return items


def _parse_json_feed(data: dict[str, Any]) -> list[FeedItem]:
    items: list[FeedItem] = []
    for raw in data.get("items") or []:
        if not isinstance(raw, dict):
            continue
        link = str(raw.get("url") or raw.get("id") or "")
        if not link:
            continue
        authors = raw.get("authors") or []
        author = None
        if authors and isinstance(authors[0], dict):
            author = authors[0].get("name")
        elif isinstance(raw.get("author"), dict):
            author = raw["author"].get("name")
        tags = raw.get("tags") or []
        tag_t = tuple(str(t) for t in tags if t)
        html = raw.get("content_html")
        text = raw.get("content_text")
        items.append(
            FeedItem(
                link=link,
                guid=str(raw.get("id") or "") or None,
                title=raw.get("title"),
                published=parse_datetime(raw.get("date_published")),
                updated=parse_datetime(raw.get("date_modified")),
                author=str(author) if author else None,
                tags=tag_t,
                content_html=str(html) if html else None,
                summary=str(text) if text and not html else (str(text) if text else None),
            )
        )
    return items
