"""Overlay ranking against committed HTML fixtures."""

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


def _article(name: str, **opts: object):
    html = (HTML / name).read_text(encoding="utf-8")
    options = ExtractOptions(**opts) if opts else ExtractOptions()
    return article_from_fetch(html, _fetch(html), options)


def test_wordpress_entry_content_is_html_article() -> None:
    art = _article("wordpress_entry_content.html")
    assert art.provenance.method == "html-article"
    assert "bias network" in art.text.lower() or "quiescent" in art.text.lower()
    assert art.title
    assert "sharedaddy" not in art.html.lower()
    assert any(m.alt == "diagram" for m in art.media) or any("foo.jpg" in m.src for m in art.media)


def test_jsonld_dek_does_not_beat_entry_content() -> None:
    art = _article("jsonld_dek_plus_entry.html")
    assert art.provenance.method == "html-article"
    assert "entry-content" in (HTML / "jsonld_dek_plus_entry.html").read_text()
    assert "Short dek text" not in art.html


def test_jsonld_only() -> None:
    art = _article("jsonld_only.html")
    assert art.provenance.method == "jsonld"
    assert "JSON-LD articleBody" in art.text or "stored only in JSON-LD" in art.text


def test_h_entry() -> None:
    art = _article("h_entry.html")
    assert art.provenance.method == "html-article"
    assert art.lang == "sv"
    assert "e-content" in (HTML / "h_entry.html").read_text()


def test_spa_empty_is_not_an_article() -> None:
    html = (HTML / "spa_empty.html").read_text(encoding="utf-8")
    with pytest.raises(NotArticleError):
        article_from_fetch(html, _fetch(html), ExtractOptions())


def test_chrome_heavy_uses_post_content() -> None:
    art = _article("chrome_heavy.html")
    assert art.provenance.method == "html-article"
    assert "soldering" in art.text.lower() or "GNU" in art.text
    assert "Related posts" not in art.html


def test_math_tex_survives() -> None:
    art = _article("math_tex_img.html")
    assert "eq.png" in art.html
    assert "data-latex" in art.html or "tex" in art.html


def test_leftover_shortcode_not_expanded() -> None:
    art = _article("leftover_shortcode.html")
    assert "[gallery" in art.html or "[gallery" in art.text


def test_category_listing_rejected() -> None:
    html = (HTML / "category_listing.html").read_text(encoding="utf-8")
    with pytest.raises(NotArticleError):
        article_from_fetch(html, _fetch(html), ExtractOptions())


def test_rss_full_content_wins() -> None:
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
    options = ExtractOptions(feed_index={canonical_key(url): item})
    art = article_from_fetch(html, _fetch(html, url), options)
    assert art.provenance.method == "rss"
    assert "radio circuits" in art.text


def test_rss_excerpt_does_not_win() -> None:
    html = (HTML / "wordpress_entry_content.html").read_text(encoding="utf-8")
    url = "https://example.com/p/fm"
    item = FeedItem(link=url, summary="Tiny excerpt.", content_html="<p>Tiny excerpt.</p>")
    options = ExtractOptions(feed_index={canonical_key(url): item})
    art = article_from_fetch(html, _fetch(html, url), options)
    assert art.provenance.method == "html-article"


def test_overlay_none_on_empty() -> None:
    assert overlay("<html><body></body></html>", url="https://example.com/") is None
