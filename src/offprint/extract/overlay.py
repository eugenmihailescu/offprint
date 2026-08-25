"""Body ranking and metadata merge."""

from __future__ import annotations

from dataclasses import dataclass, field

from offprint.constants import DEFAULT_MIN_TEXT_CHARS
from offprint.dates import parse_datetime
from offprint.extract.feeds_match import FeedItem
from offprint.extract.hentry import article_html
from offprint.extract.htmlutil import drop_chrome, parse_html, strip_text
from offprint.extract.jsonld import (
    article_nodes,
    as_plain_paragraphs,
    jsonld_body_html,
    jsonld_body_is_tagged,
    text_len,
)
from offprint.extract.metadata import Meta, collect_metadata
from offprint.extract.trafilatura_ext import extract_html as trafi_html
from offprint.extract.trafilatura_ext import extract_metadata_fallback
from offprint.model import Method


@dataclass
class OverlayResult:
    html: str
    method: Method
    method_chain: list[str] = field(default_factory=list)
    meta: Meta = field(default_factory=Meta)


def is_listing(html: str, text: str) -> bool:
    from lxml import html as lhtml

    if not html.strip():
        return False
    try:
        tree = lhtml.fragment_fromstring(html, create_parent="div")
    except Exception:
        tree = parse_html(html)
    anchors = tree.xpath(".//a")
    if len(anchors) < 5:
        return False
    anchor_chars = sum(len(strip_text(a)) for a in anchors)
    return (anchor_chars / max(len(text), 1)) > 0.5


def is_substantial(html: str, *, min_text_chars: int) -> bool:
    text = strip_text(html)
    if is_listing(html, text):
        return False
    imgs = html.lower().count("<img") + html.lower().count("<figure")
    if len(text) >= min_text_chars:
        return True
    return imgs >= 2 and len(text) >= 80


def _rss_body(item: FeedItem | None, *, min_text_chars: int) -> str | None:
    if item is None or not item.content_html:
        return None
    html = item.content_html
    if not is_substantial(html, min_text_chars=min_text_chars):
        return None
    summary = item.summary or ""
    body_len = text_len(html)
    sum_len = text_len(summary) if summary else 0
    if sum_len and body_len < max(1.5 * sum_len, min_text_chars) and body_len <= sum_len:
        return None
    if sum_len and body_len < 1.5 * sum_len and body_len < min_text_chars:
        return None
    return html


def overlay(
    html: str,
    *,
    url: str,
    feed: FeedItem | None = None,
    min_text_chars: int = DEFAULT_MIN_TEXT_CHARS,
) -> OverlayResult | None:
    tree = parse_html(html)
    chain: list[str] = []
    meta = collect_metadata(tree)
    json_nodes = article_nodes(tree)
    drop_chrome(tree, inside_article=False)

    html_article = article_html(tree)
    json_html = jsonld_body_html(json_nodes[0]) if json_nodes else None
    rss_html = _rss_body(feed, min_text_chars=min_text_chars)

    winner: str | None = None
    method: Method | None = None

    if rss_html and is_substantial(rss_html, min_text_chars=min_text_chars):
        winner, method = rss_html, "rss"
        chain.append("rss")
    if html_article:
        chain.append("html-article")
        if method is None and is_substantial(html_article, min_text_chars=min_text_chars):
            winner, method = html_article, "html-article"
    if json_html:
        chain.append("jsonld")
        if method is None:
            if jsonld_body_is_tagged(json_html):
                if is_substantial(json_html, min_text_chars=min_text_chars):
                    winner, method = json_html, "jsonld"
            elif is_substantial(as_plain_paragraphs(json_html), min_text_chars=min_text_chars):
                winner, method = as_plain_paragraphs(json_html), "jsonld"
        elif method == "html-article" and html_article and jsonld_body_is_tagged(json_html):
            if is_substantial(json_html, min_text_chars=min_text_chars) and text_len(
                json_html
            ) >= 1.5 * text_len(html_article):
                winner, method = json_html, "jsonld"

    listing_page = bool(html_article and is_listing(html_article, strip_text(html_article)))
    if method is None and not listing_page:
        trafi = trafi_html(html, url)
        chain.append("trafilatura")
        if trafi and is_substantial(trafi, min_text_chars=min_text_chars):
            winner, method = trafi, "trafilatura"

    if feed:
        chain.append("rss")
        if not meta.title and feed.title:
            meta.title = feed.title
        if not meta.published_at and feed.published:
            meta.published_at = parse_datetime(feed.published)
        if not meta.updated_at and feed.updated:
            meta.updated_at = parse_datetime(feed.updated)
        if not meta.author_names and feed.author:
            meta.author_names = [feed.author]
        if not meta.tags and feed.tags:
            meta.tags = list(feed.tags)
        if not meta.categories and feed.categories:
            meta.categories = list(feed.categories)
        if not meta.excerpt and feed.summary and method != "rss":
            meta.excerpt = strip_text(feed.summary)[:4000]

    fallback = extract_metadata_fallback(html, url)
    if not meta.title and fallback.get("title"):
        meta.title = str(fallback["title"])
        chain.append("trafilatura")
    if not meta.published_at and fallback.get("publishedAt"):
        meta.published_at = parse_datetime(fallback["publishedAt"])
    if not meta.author_names and fallback.get("author"):
        meta.author_names = [str(fallback["author"])]
    if not meta.lang and fallback.get("lang"):
        meta.lang = str(fallback["lang"])
    if not meta.excerpt and fallback.get("excerpt"):
        meta.excerpt = str(fallback["excerpt"])

    if method is None or not winner:
        return None
    meta.sources = list(dict.fromkeys(meta.sources + chain))
    return OverlayResult(
        html=winner,
        method=method,
        method_chain=list(dict.fromkeys(chain)),
        meta=meta,
    )
