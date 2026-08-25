"""nh3 sanitizer and URL policy for article HTML fragments."""

from __future__ import annotations

from urllib.parse import urljoin, urlparse

import nh3
from lxml import html as lhtml

from offprint.extract.htmlutil import parse_html, strip_text

ALLOW_TAGS = {
    "p",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "ul",
    "ol",
    "li",
    "blockquote",
    "pre",
    "code",
    "kbd",
    "br",
    "hr",
    "a",
    "img",
    "figure",
    "figcaption",
    "table",
    "thead",
    "tbody",
    "tfoot",
    "tr",
    "th",
    "td",
    "caption",
    "strong",
    "b",
    "em",
    "i",
    "s",
    "strike",
    "sub",
    "sup",
    "mark",
    "q",
    "cite",
    "abbr",
    "time",
    "span",
    "div",
    "section",
    "article",
    "aside",
    "iframe",
    "video",
    "audio",
    "source",
    "picture",
}
_URL_ATTRS = frozenset({"href", "src"})
_SAFE_SCHEMES = frozenset({"http", "https", "mailto"})
_EMBED_HOSTS = frozenset(
    {
        "youtube.com",
        "youtube-nocookie.com",
        "youtu.be",
        "vimeo.com",
        "player.vimeo.com",
    }
)
_ATTRS: dict[str, set[str]] = {
    "*": {
        "title",
        "lang",
        "role",
        "aria-label",
        "aria-hidden",
        "datetime",
        "width",
        "height",
    },
    "a": {"href", "rel", "target"},
    "img": {"src", "srcset", "sizes", "alt", "class", "data-latex", "data-display"},
    "iframe": {"src"},
    "video": {"src", "poster", "controls", "controlslist", "preload"},
    "audio": {"src", "controls", "preload"},
    "source": {"src", "type"},
    "code": {"class"},
    "pre": {"class"},
    "span": {"class", "data-latex", "data-display"},
    "div": {"class"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan"},
    "ol": {"start", "type"},
    "li": {"value"},
}


def _host(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def is_safe_embed(url: str) -> bool:
    return _host(url) in _EMBED_HOSTS


def _rewrite_url(value: str, base: str) -> str | None:
    raw = value.strip()
    if not raw:
        return None
    if raw.startswith("#"):
        return raw
    if raw.startswith("//"):
        raw = "https:" + raw
    abs_url = urljoin(base, raw)
    parsed = urlparse(abs_url)
    if parsed.scheme in _SAFE_SCHEMES:
        return abs_url
    return None


def _prep_iframes(html: str, base: str) -> str:
    try:
        tree = parse_html(html)
    except Exception:
        return html
    for iframe in list(tree.xpath("//iframe")):
        src = iframe.get("src") or ""
        rewritten = _rewrite_url(src, base)
        if rewritten and is_safe_embed(rewritten):
            iframe.set("src", rewritten)
            continue
        parent = iframe.getparent()
        if parent is None:
            continue
        if rewritten:
            a = lhtml.Element("a", href=rewritten)
            a.text = rewritten
            parent.replace(iframe, a)
        else:
            parent.remove(iframe)
    body = tree.find("body")
    target = body if body is not None else tree
    return "".join(
        [target.text or ""]
        + [lhtml.tostring(child, encoding="unicode", method="html") for child in target]
    )


def sanitize(html: str, *, base_url: str) -> str:
    prepped = _prep_iframes(html, base_url)

    def attr_filter(tag: str, attr: str, value: str) -> str | None:
        if attr.lower() in _URL_ATTRS or (tag == "iframe" and attr == "src"):
            return _rewrite_url(value, base_url)
        return value

    attrs = {tag: set(vals) for tag, vals in _ATTRS.items()}
    cleaned = nh3.clean(
        prepped,
        tags=ALLOW_TAGS,
        attributes=attrs,
        attribute_filter=attr_filter,
        url_schemes=_SAFE_SCHEMES | {"https", "http", "mailto"},
        link_rel=None,
        strip_comments=True,
    )
    tree = parse_html(cleaned)
    body = tree.find("body")
    if body is not None:
        from offprint.extract.htmlutil import inner_html

        return inner_html(body).strip()
    return cleaned.strip()


def html_to_text(html: str) -> str:
    return strip_text(html)
