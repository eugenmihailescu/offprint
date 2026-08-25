"""Open Graph, twitter, HTML, and JSON-LD metadata fill."""

from __future__ import annotations

from dataclasses import dataclass, field

from lxml.html import HtmlElement

from offprint.dates import parse_datetime
from offprint.extract.htmlutil import class_xpath, strip_text
from offprint.extract.jsonld import (
    jsonld_image_urls,
    jsonld_names,
    jsonld_str,
    meta_nodes,
)


@dataclass
class Meta:
    title: str = ""
    published_at: str | None = None
    updated_at: str | None = None
    author_names: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    lang: str | None = None
    excerpt: str | None = None
    images: list[str] = field(default_factory=list)
    canonical: str | None = None
    sources: list[str] = field(default_factory=list)


def _meta(tree: HtmlElement, *, prop: str | None = None, name: str | None = None) -> str | None:
    if prop:
        vals = tree.xpath(f"//meta[@property='{prop}']/@content")
        if vals and str(vals[0]).strip():
            return str(vals[0]).strip()
    if name:
        vals = tree.xpath(f"//meta[@name='{name}']/@content")
        if vals and str(vals[0]).strip():
            return str(vals[0]).strip()
    return None


def _first_text(tree: HtmlElement, xpath: str) -> str | None:
    found = tree.xpath(xpath)
    if not found:
        return None
    el = found[0]
    if hasattr(el, "get"):
        text = strip_text(el)
    else:
        text = str(el).strip()
    return text or None


def _split_title(title: str) -> str:
    for sep in (" · ", " – ", " — ", " - "):
        if sep in title:
            return title.rsplit(sep, 1)[0].strip() or title
    return title


def collect_metadata(tree: HtmlElement) -> Meta:
    meta = Meta()
    nodes = meta_nodes(tree)
    primary = nodes[0] if nodes else {}

    def take(field: str, value: str | None, source: str) -> None:
        if not value:
            return
        current = getattr(meta, field)
        if field in {"author_names", "tags", "categories", "images", "sources"}:
            return
        if not current:
            setattr(meta, field, value)
            if source not in meta.sources:
                meta.sources.append(source)

    headline = jsonld_str(primary.get("headline") or primary.get("name"))
    take("title", headline, "jsonld")
    take("title", _meta(tree, prop="og:title"), "og")
    take("title", _meta(tree, name="twitter:title"), "og")
    entry_title = _first_text(tree, class_xpath("entry-title") + "|" + class_xpath("p-name"))
    take("title", entry_title, "html-article")
    raw_title = _first_text(tree, "//title")
    take("title", _split_title(raw_title) if raw_title else None, "html-article")

    take("published_at", parse_datetime(jsonld_str(primary.get("datePublished"))), "jsonld")
    take("published_at", parse_datetime(_meta(tree, prop="article:published_time")), "og")
    pub_time = tree.xpath(
        "//time[contains(@class,'published')]/@datetime"
        "|//time[contains(@class,'dt-published')]/@datetime"
        "|" + class_xpath("dt-published") + "/@datetime"
    )
    if pub_time:
        take("published_at", parse_datetime(str(pub_time[0])), "html-article")

    take("updated_at", parse_datetime(jsonld_str(primary.get("dateModified"))), "jsonld")
    take("updated_at", parse_datetime(_meta(tree, prop="article:modified_time")), "og")

    authors = jsonld_names(primary.get("author"))
    if authors:
        meta.author_names = authors
        meta.sources.append("jsonld")
    if not meta.author_names:
        rel = [_first_text(tree, "//a[@rel='author']"), _first_text(tree, class_xpath("p-author"))]
        names = [n for n in rel if n]
        if not names:
            a = _meta(tree, name="author")
            if a:
                names = [a]
        if names:
            meta.author_names = names
            meta.sources.append("html-article")

    keywords = jsonld_str(primary.get("keywords"))
    if keywords:
        meta.tags = [p.strip() for p in keywords.split(",") if p.strip()]
        meta.sources.append("jsonld")
    if not meta.tags:
        tags = [
            str(t).strip()
            for t in tree.xpath("//meta[@property='article:tag']/@content")
            if str(t).strip()
        ]
        if not tags:
            tags = [
                strip_text(el)
                for el in tree.xpath("//a[@rel='tag']|" + class_xpath("p-category"))
                if strip_text(el)
            ]
        if tags:
            meta.tags = tags
            meta.sources.append("og")

    section = jsonld_str(primary.get("articleSection"))
    if section:
        meta.categories = [section]
        meta.sources.append("jsonld")

    lang = tree.get("lang") or _first_text(tree, "//html/@lang")
    if not lang:
        html_el = tree.xpath("/html")
        if html_el:
            lang = html_el[0].get("lang")
    take(
        "lang",
        lang or jsonld_str(primary.get("inLanguage")) or _meta(tree, name="content-language"),
        "html-article",
    )

    take("excerpt", jsonld_str(primary.get("description")), "jsonld")
    take("excerpt", _meta(tree, prop="og:description"), "og")
    take("excerpt", _meta(tree, name="description"), "og")

    images: list[str] = []
    images.extend(jsonld_image_urls(primary.get("image")))
    og_img = _meta(tree, prop="og:image")
    if og_img:
        images.append(og_img)
    meta.images = list(dict.fromkeys(images))

    canon = tree.xpath("//link[@rel='canonical']/@href")
    if canon and str(canon[0]).strip():
        meta.canonical = str(canon[0]).strip()
        meta.sources.append("html-article")
    elif jsonld_str(primary.get("url")):
        meta.canonical = jsonld_str(primary.get("url"))
        meta.sources.append("jsonld")
    return meta
