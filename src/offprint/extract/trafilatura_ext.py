"""Call trafilatura.extract / extract_metadata on already-fetched HTML only."""

from __future__ import annotations

from typing import Any

import trafilatura

from offprint.extract.htmlutil import parse_html, strip_text


def extract_html(html: str, url: str | None = None) -> str | None:
    out = trafilatura.extract(
        html,
        url=url,
        output_format="html",
        include_comments=False,
        include_tables=True,
        include_images=True,
        include_links=True,
        include_formatting=True,
        favor_recall=True,
    )
    if out and out.strip():
        return out
    txt = trafilatura.extract(
        html,
        url=url,
        output_format="txt",
        include_comments=False,
        favor_recall=True,
    )
    if txt and strip_text(txt):
        import html as html_lib

        return f"<p>{html_lib.escape(txt.strip())}</p>"
    return None


def extract_metadata_fallback(html: str, url: str | None = None) -> dict[str, Any]:
    doc = trafilatura.extract_metadata(parse_html(html), default_url=url)
    if doc is None:
        return {}
    return {
        "title": getattr(doc, "title", None),
        "publishedAt": getattr(doc, "date", None),
        "author": getattr(doc, "author", None),
        "lang": getattr(doc, "language", None),
        "excerpt": getattr(doc, "description", None),
    }
