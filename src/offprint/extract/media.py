"""Catalog images and embeds from sanitized HTML plus OG/JSON-LD URLs."""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from offprint.constants import MEDIA_SRC_MAX_LENGTH
from offprint.extract.htmlutil import parse_html
from offprint.extract.sanitize import is_safe_embed
from offprint.model import Media, MediaRole

_SIZE_SUFFIX = re.compile(r"-\d+x\d+(?=\.[A-Za-z0-9]+$)")


def _dedup_key(src: str) -> str:
    path = urlparse(src).path
    return _SIZE_SUFFIX.sub("", path) or src


def _int(value: str | None) -> int | None:
    if not value:
        return None
    try:
        n = int(re.split(r"\D", value, maxsplit=1)[0])
    except (TypeError, ValueError):
        return None
    return n if n >= 0 else None


def catalog_media(html: str, *, extra: list[str], base_url: str) -> list[Media]:
    tree = parse_html(html)
    items: list[Media] = []
    seen: set[str] = set()

    def add(
        src: str,
        *,
        role: MediaRole,
        alt: str | None = None,
        title: str | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> None:
        abs_src = urljoin(base_url, src.strip())
        if len(abs_src) > MEDIA_SRC_MAX_LENGTH:
            return
        key = _dedup_key(abs_src)
        if key in seen:
            return
        seen.add(key)
        items.append(
            Media(src=abs_src, alt=alt, title=title, width=width, height=height, role=role)
        )

    for img in tree.xpath("//img[@src]"):
        add(
            img.get("src") or "",
            role="inline",
            alt=img.get("alt"),
            title=img.get("title"),
            width=_int(img.get("width")),
            height=_int(img.get("height")),
        )
    for iframe in tree.xpath("//iframe[@src]"):
        src = iframe.get("src") or ""
        if is_safe_embed(urljoin(base_url, src)):
            add(src, role="embed")
    for video in tree.xpath("//video[@src]|//source[@src]"):
        add(video.get("src") or "", role="embed")

    for src in extra:
        add(src, role="og")
    if items:
        # first OG/JSON-LD image that is not already inline becomes feature if no feature
        for item in items:
            if item.role == "og":
                item.role = "feature"
                break
    return items
