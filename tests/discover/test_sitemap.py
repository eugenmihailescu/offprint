from pathlib import Path

from offprint.discover.classify import should_queue
from offprint.discover.sitemap import parse_sitemap_xml

FIX = Path(__file__).resolve().parents[2] / "fixtures" / "sitemaps"


def test_yyyy_mm_and_taxonomy() -> None:
    kind, locs = parse_sitemap_xml((FIX / "posts_yyyy_mm.xml").read_bytes())
    assert kind == "urlset"
    queued = [u for u in locs if should_queue(u)]
    assert "https://example.com/2020/06/slug" in queued
    kind, locs = parse_sitemap_xml((FIX / "taxonomy.xml").read_bytes())
    queued = [u for u in locs if should_queue(u)]
    assert "https://example.com/blog/real-post" in queued
    assert "https://example.com/category/foo" not in queued


def test_feedback() -> None:
    _, locs = parse_sitemap_xml((FIX / "feedback.xml").read_bytes())
    queued = [u for u in locs if should_queue(u)]
    assert queued == ["https://example.com/feedback/my-post"]


def test_home_only() -> None:
    _, locs = parse_sitemap_xml((FIX / "home_only.xml").read_bytes())
    assert locs == ["https://example.com/"]
    assert should_queue(locs[0], only_home=True)


def test_xxe_not_expanded() -> None:
    _, locs = parse_sitemap_xml((FIX / "xxe.xml").read_bytes())
    blob = "\n".join(locs)
    assert "root:" not in blob
    assert "/etc/passwd" not in blob
    assert any("safe-post" in u for u in locs)


def test_index_lists_child() -> None:
    kind, locs = parse_sitemap_xml((FIX / "index_www.xml").read_bytes())
    assert kind == "index"
    assert locs == ["https://www.example.com/sitemap-posts.xml"]
