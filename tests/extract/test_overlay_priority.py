"""Explicit overlay ranking: rss vs html-article vs jsonld vs trafilatura."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from offprint.errors import NotArticleError
from offprint.extract.feeds_match import FeedItem
from offprint.extract.overlay import overlay
from offprint.fetch import FetchResult
from offprint.pipeline import ExtractOptions, article_from_fetch
from offprint.urls import canonical_key

HTML = Path(__file__).resolve().parents[2] / "fixtures" / "html"


def _fetch(html: str, url: str = "https://example.com/p/fm") -> FetchResult:
    return FetchResult(
        requested_url=url,
        final_url=url,
        status=200,
        content_type="text/html",
        body=html.encode("utf-8"),
        redirects=(),
        fetched_at=datetime(2026, 8, 25, 12, 0, tzinfo=UTC),
    )


def test_rss_full_content_beats_empty_dom() -> None:
    html = (HTML / "spa_empty.html").read_text(encoding="utf-8")
    url = "https://example.com/p/fm"
    item = FeedItem(
        link=url,
        title="From the feed",
        summary="Short summary.",
        content_html=(
            "<p>Feed full content is much longer than the summary and includes enough "
            "sentences about radio circuits and Linux so Offprint should prefer rss "
            "as the body winner when this item is injected for the URL.</p>"
            "<p>Second feed paragraph still counting toward substantial text.</p>"
        ),
    )
    art = article_from_fetch(
        html,
        _fetch(html, url),
        ExtractOptions(feed_index={canonical_key(url): item}),
    )
    assert art.provenance.method == "rss"
    assert "html-article" not in art.provenance.methodChain or art.provenance.method == "rss"


def test_rss_excerpt_does_not_beat_entry_content() -> None:
    html = (HTML / "wordpress_entry_content.html").read_text(encoding="utf-8")
    url = "https://example.com/p/fm"
    item = FeedItem(link=url, summary="Tiny excerpt.", content_html="<p>Tiny excerpt.</p>")
    art = article_from_fetch(
        html,
        _fetch(html, url),
        ExtractOptions(feed_index={canonical_key(url): item}),
    )
    assert art.provenance.method == "html-article"


def test_jsonld_dek_loses_to_entry_content() -> None:
    html = (HTML / "jsonld_dek_plus_entry.html").read_text(encoding="utf-8")
    result = overlay(html, url="https://example.com/p")
    assert result is not None
    assert result.method == "html-article"
    assert "jsonld" in result.method_chain


def test_jsonld_wins_without_article_node() -> None:
    html = (HTML / "jsonld_only.html").read_text(encoding="utf-8")
    result = overlay(html, url="https://example.com/p")
    assert result is not None
    assert result.method == "jsonld"


def test_listing_does_not_fall_through_to_trafilatura() -> None:
    html = (HTML / "category_listing.html").read_text(encoding="utf-8")
    assert overlay(html, url="https://example.com/category/foo") is None
    with pytest.raises(NotArticleError):
        article_from_fetch(html, _fetch(html), ExtractOptions())
