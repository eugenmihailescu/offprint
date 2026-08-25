"""JSON-LD BlogPosting / Article extraction."""

from __future__ import annotations

import json
from typing import Any

from lxml.html import HtmlElement

from offprint.extract.htmlutil import strip_text

ARTICLE_TYPES = frozenset(
    {
        "BlogPosting",
        "Article",
        "NewsArticle",
        "TechArticle",
        "ScholarlyArticle",
        "SocialMediaPosting",
    }
)
META_ONLY_TYPES = frozenset({"WebPage", "CollectionPage", "ItemList"})


def _types_of(node: dict[str, Any]) -> set[str]:
    raw = node.get("@type")
    if isinstance(raw, str):
        return {raw.split("/")[-1]}
    if isinstance(raw, list):
        out: set[str] = set()
        for item in raw:
            if isinstance(item, str):
                out.add(item.split("/")[-1])
        return out
    return set()


def iter_nodes(data: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(data, list):
        for item in data:
            found.extend(iter_nodes(item))
    elif isinstance(data, dict):
        if "@graph" in data:
            found.extend(iter_nodes(data["@graph"]))
        found.append(data)
    return found


def load_jsonld_blocks(tree: HtmlElement) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for script in tree.xpath("//script[@type='application/ld+json']"):
        raw = (script.text or "").strip()
        if not raw:
            raw = "".join(script.itertext()).strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        blocks.extend(iter_nodes(data))
    return blocks


def article_nodes(tree: HtmlElement) -> list[dict[str, Any]]:
    return [n for n in load_jsonld_blocks(tree) if _types_of(n) & ARTICLE_TYPES]


def meta_nodes(tree: HtmlElement) -> list[dict[str, Any]]:
    wanted = ARTICLE_TYPES | META_ONLY_TYPES
    return [n for n in load_jsonld_blocks(tree) if _types_of(n) & wanted]


def jsonld_body_html(node: dict[str, Any]) -> str | None:
    body = node.get("articleBody") or node.get("text")
    if not isinstance(body, str) or not body.strip():
        return None
    return body


def jsonld_body_is_tagged(html: str) -> bool:
    low = html.lower()
    return any(tok in low for tok in ("<p", "<div", "<br", "<h"))


def as_plain_paragraphs(text: str) -> str:
    import html as html_lib

    chunks = [c.strip() for c in text.split("\n\n") if c.strip()]
    if not chunks:
        chunks = [text.strip()] if text.strip() else []
    return "".join(f"<p>{html_lib.escape(c)}</p>" for c in chunks)


def jsonld_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        for key in ("name", "headline", "@value", "url"):
            if isinstance(value.get(key), str) and value[key].strip():
                return value[key].strip()
    if isinstance(value, list):
        for item in value:
            got = jsonld_str(item)
            if got:
                return got
    return None


def jsonld_names(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        names: list[str] = []
        for item in value:
            names.extend(jsonld_names(item))
        return names
    if isinstance(value, dict):
        name = jsonld_str(value.get("name") or value)
        return [name] if name else []
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def jsonld_image_urls(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    if isinstance(value, dict):
        url = jsonld_str(value.get("url") or value.get("contentUrl") or value)
        return [url] if url else []
    if isinstance(value, list):
        urls: list[str] = []
        for item in value:
            urls.extend(jsonld_image_urls(item))
        return urls
    return []


def text_len(html: str) -> int:
    return len(strip_text(html))
