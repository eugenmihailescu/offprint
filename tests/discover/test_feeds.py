from pathlib import Path

from offprint.discover.feeds import parse_feed

FIX = Path(__file__).resolve().parents[2] / "fixtures" / "feeds"


def test_rss_full_content() -> None:
    items = parse_feed((FIX / "rss_full.xml").read_bytes(), content_type="application/rss+xml")
    assert items
    assert items[0].content_html
    assert "radio circuits" in items[0].content_html
    assert items[0].summary is None or "Short summary" in (items[0].summary or "")


def test_atom_excerpt_no_html() -> None:
    items = parse_feed((FIX / "atom_excerpt.xml").read_bytes(), content_type="application/atom+xml")
    assert items
    assert items[0].link.endswith("/excerpt-post")
    assert not items[0].content_html
    assert items[0].summary


def test_json_feed() -> None:
    items = parse_feed((FIX / "jsonfeed.json").read_bytes(), content_type="application/feed+json")
    assert items[0].link == "https://example.com/json-post"
    assert items[0].content_html
    assert items[0].author == "Ada"
    assert "json" in items[0].tags
