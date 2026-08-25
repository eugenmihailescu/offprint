"""Golden quality bar: method, title, text, headings, images, math."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import pytest

from offprint.errors import NotArticleError
from offprint.extract.htmlutil import parse_html
from offprint.fetch import FetchResult
from offprint.model import Article
from offprint.pipeline import ExtractOptions, article_from_fetch

ROOT = Path(__file__).resolve().parents[2]
HTML = ROOT / "fixtures" / "html"
EXPECTED = ROOT / "fixtures" / "expected"


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


def normalize_article(article: Article) -> dict[str, object]:
    """Stable snapshot: drop run-varying provenance clocks/versions."""
    data = article.model_dump(mode="json", exclude_none=False)
    prov = data["provenance"]
    prov["fetchedAt"] = "2000-01-01T00:00:00Z"
    prov["extractorVersion"] = "offprint/test"
    prov["rawHtmlSha256"] = None
    prov["rawHtmlPath"] = None
    prov["bytes"] = 0
    return data


def _extract(name: str) -> Article:
    html = (HTML / name).read_text(encoding="utf-8")
    return article_from_fetch(html, _fetch(html), ExtractOptions())


def _stems(article: Article) -> list[str]:
    return [Path(urlparse(m.src).path).name for m in article.media if urlparse(m.src).path]


def _heading_count(html: str) -> int:
    tree = parse_html(html)
    return len(tree.xpath("//h1|//h2|//h3|//h4|//h5|//h6"))


def test_expected_specs_cover_html_fixtures() -> None:
    html_files = {p.name for p in HTML.glob("*.html")}
    errors = json.loads((EXPECTED / "not_an_article.json").read_text(encoding="utf-8"))
    covered = set(errors["fixtures"])
    for spec in EXPECTED.glob("*.json"):
        if spec.name == "not_an_article.json":
            continue
        covered.add(spec.stem + ".html")
    missing = html_files - covered
    assert not missing, f"fixtures without expected specs: {sorted(missing)}"


@pytest.mark.parametrize(
    "spec_path",
    sorted(p for p in EXPECTED.glob("*.json") if p.name != "not_an_article.json"),
    ids=lambda p: p.stem,
)
def test_golden_quality(spec_path: Path) -> None:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    article = _extract(spec_path.stem + ".html")
    snapshot = normalize_article(article)
    assert snapshot["provenance"]["method"] == spec["method"]
    assert article.title == spec["title"]
    assert article.lang == spec["lang"]
    assert article.authorNames == spec["authorNames"]
    text = article.text
    for needle in spec["textContains"]:
        assert needle in text, f"missing {needle!r} in text"
    assert _heading_count(article.html) >= spec["minHeadings"]
    stems = _stems(article)
    for stem in spec["imageStems"]:
        assert stem in stems, f"missing image stem {stem} in {stems}"
    for needle in spec["htmlContains"]:
        assert needle in article.html, f"missing {needle!r} in html"
    for needle in spec["htmlNotContains"]:
        assert needle not in article.html, f"unexpected {needle!r} in html"


def test_not_an_article_fixtures() -> None:
    names = json.loads((EXPECTED / "not_an_article.json").read_text(encoding="utf-8"))["fixtures"]
    for name in names:
        html = (HTML / name).read_text(encoding="utf-8")
        with pytest.raises(NotArticleError):
            article_from_fetch(html, _fetch(html), ExtractOptions())
