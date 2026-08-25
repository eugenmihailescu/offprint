"""Catalog images and embeds from sanitized HTML plus OG/JSON-LD URLs."""

from __future__ import annotations

import hashlib
import logging
import mimetypes
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

from offprint.constants import (
    MEDIA_DOWNLOAD_MAX_BYTES,
    MEDIA_PROBE_MAX_BYTES,
    MEDIA_PROBE_TIMEOUT_SEC,
    MEDIA_SRC_MAX_LENGTH,
)
from offprint.errors import BlockedUrlError, OffprintError
from offprint.extract.htmlutil import parse_html
from offprint.extract.sanitize import is_safe_embed
from offprint.fetch import FetchClient
from offprint.model import Media, MediaRole

log = logging.getLogger("offprint.extract.media")

_SAFE_EXT = re.compile(r"^\.[A-Za-z0-9]{1,8}$")
_SKIP_EXT = frozenset({".html", ".htm", ".php", ".asp", ".aspx"})

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


def _mime(content_type: str | None) -> str | None:
    if not content_type:
        return None
    mime = content_type.split(";", 1)[0].strip()[:127]
    return mime or None


def guess_media_ext(url: str, content_type: str | None) -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    if _SAFE_EXT.match(suffix) and suffix not in _SKIP_EXT:
        return suffix
    mime = _mime(content_type)
    if mime:
        ext = mimetypes.guess_extension(mime)
        if ext == ".jpe":
            ext = ".jpg"
        if ext and _SAFE_EXT.match(ext) and ext not in _SKIP_EXT:
            return ext
    return ".bin"


async def enrich_media(
    items: list[Media],
    client: FetchClient,
    *,
    probe: bool = False,
    download_dir: Path | None = None,
) -> None:
    """Fill mime/size and optionally write ``{sha256}.{ext}``. Failures are warnings."""
    if not probe and download_dir is None:
        return
    if download_dir is not None:
        download_dir.mkdir(parents=True, exist_ok=True)
    seen_src: set[str] = set()
    for item in items:
        if item.role == "embed":
            continue
        src = (item.src or "").strip()
        if not src or src in seen_src:
            continue
        seen_src.add(src)
        if download_dir is not None:
            await _download_one(item, client, download_dir)
        if probe and (item.mimeType is None or item.byteSize is None):
            await _probe_one(item, client)


async def _probe_one(item: Media, client: FetchClient) -> None:
    url = item.src
    try:
        result = await client.head(url, timeout=MEDIA_PROBE_TIMEOUT_SEC)
        _apply_probe(item, result.content_type, result.content_length)
    except BlockedUrlError:
        log.warning("media probe blocked %s", url)
        return
    except OffprintError as exc:
        log.debug("media HEAD %s: %s", url, exc.message)
    if item.mimeType is not None and item.byteSize is not None:
        return
    try:
        result = await client.get(
            url,
            timeout=MEDIA_PROBE_TIMEOUT_SEC,
            max_bytes=MEDIA_PROBE_MAX_BYTES,
            headers={"Range": "bytes=0-0"},
        )
        size = result.content_length
        if size is None and result.body:
            size = len(result.body)
        _apply_probe(item, result.content_type, size)
    except OffprintError as exc:
        log.warning("media probe failed %s: %s", url, exc.message)


async def _download_one(item: Media, client: FetchClient, dest: Path) -> None:
    url = item.src
    try:
        result = await client.get(url, max_bytes=MEDIA_DOWNLOAD_MAX_BYTES)
    except OffprintError as exc:
        log.warning("media download failed %s: %s", url, exc.message)
        return
    sha = hashlib.sha256(result.body).hexdigest()
    ext = guess_media_ext(url, result.content_type)
    path = dest / f"{sha}{ext}"
    if not path.exists():
        path.write_bytes(result.body)
    if item.mimeType is None:
        item.mimeType = _mime(result.content_type)
    if item.byteSize is None:
        item.byteSize = len(result.body)


def _apply_probe(item: Media, content_type: str | None, size: int | None) -> None:
    if item.mimeType is None:
        item.mimeType = _mime(content_type)
    if item.byteSize is None and size is not None:
        item.byteSize = size
