"""lxml helpers: parse, chrome strip, serialize, text."""

from __future__ import annotations

import re

from lxml import html as lhtml
from lxml.html import HtmlElement

_CHROME_RE = re.compile(
    r"(share|related|addthis|sharedaddy|yarpp|jp-relatedposts|ts-fab|wpcnt|"
    r"cookie|newsletter|sidebar)",
    re.I,
)
_WS = re.compile(r"\s+")


def parse_html(raw: str) -> HtmlElement:
    text = raw.strip() or "<html><body></body></html>"
    try:
        return lhtml.document_fromstring(text)
    except Exception:
        return lhtml.fragment_fromstring(text, create_parent="body")


def class_has(el: HtmlElement, name: str) -> bool:
    return name in (el.get("class") or "").split()


def class_xpath(name: str) -> str:
    return f"//*[contains(concat(' ', normalize-space(@class), ' '), ' {name} ')]"


def serialize(el: HtmlElement) -> str:
    return lhtml.tostring(el, encoding="unicode", method="html")


def inner_html(el: HtmlElement) -> str:
    parts = [el.text or ""]
    parts.extend(serialize(child) for child in el)
    return "".join(parts)


def strip_text(html_or_el: str | HtmlElement) -> str:
    if isinstance(html_or_el, str):
        if not html_or_el.strip():
            return ""
        el = parse_html(html_or_el)
    else:
        el = html_or_el
    return _WS.sub(" ", (el.text_content() or "")).strip()


def drop_chrome(tree: HtmlElement, *, inside_article: bool) -> None:
    for xp in ("//script", "//style", "//noscript"):
        for el in tree.xpath(xp):
            el.drop_tree()
    if not inside_article:
        for xp in ("//nav", "//footer", "//form"):
            for el in tree.xpath(xp):
                el.drop_tree()
        for el in tree.xpath(
            "//div[contains(concat(' ', normalize-space(@class), ' '), ' tags ')]"
            "|//p[contains(concat(' ', normalize-space(@class), ' '), ' tags ')]"
        ):
            el.drop_tree()
    for el in list(tree.xpath("//*[@class or @id]")):
        blob = f"{el.get('class') or ''} {el.get('id') or ''}"
        if _CHROME_RE.search(blob):
            el.drop_tree()


def count_tags(html: str, tag: str) -> int:
    if not html.strip():
        return 0
    tree = parse_html(html)
    return len(tree.xpath(f"//{tag}"))
