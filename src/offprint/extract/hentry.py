"""Pick the main article node (h-entry, entry-content, article)."""

from __future__ import annotations

from lxml.html import HtmlElement

from offprint.extract.htmlutil import class_xpath, drop_chrome, inner_html

_E_CONTENT = ".//*[contains(concat(' ', normalize-space(@class), ' '), ' e-content ')]"


def article_node(tree: HtmlElement) -> HtmlElement | None:
    for xp in (
        f"{class_xpath('h-entry')}//{_E_CONTENT[3:]}",
        class_xpath("e-content"),
        class_xpath("entry-content"),
        class_xpath("post-content"),
        class_xpath("article-content"),
        "//*[@itemprop='articleBody']",
        "//article",
    ):
        found = tree.xpath(xp)
        if found:
            return found[0]
    return None


def article_html(tree: HtmlElement) -> str | None:
    node = article_node(tree)
    if node is None:
        return None
    drop_chrome(node, inside_article=True)
    html = inner_html(node).strip()
    return html or None
