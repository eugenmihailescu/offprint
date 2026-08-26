"""Deny-list URL classification (not an allow-list of permalink shapes)."""

from __future__ import annotations

import fnmatch
import re
from urllib.parse import parse_qs, urlparse

_PAGE = re.compile(r"/page(s)?/\d+$")
_ASSET = re.compile(
    r"\.(?:jpe?g|png|gif|webp|svg|avif|heic|heif|bmp|ico|mp4|mp3|pdf|zip)(?:$|\?)",
    re.I,
)
DENY_PREFIXES = (
    "/tag/",
    "/tags/",
    "/category/",
    "/categories/",
    "/author/",
    "/authors/",
    "/search",
    "/search/",
    "/wp-admin",
    "/wp-json",
    "/wp-login",
    "/cart/",
    "/checkout/",
    "/account/",
    "/comments/feed",
    "/feed",
    "/feed/",
    "/cdn-cgi/",
    "/products/",
    "/product/",
    "/collections/",
    "/collection/",
)


def normalized_path(url: str) -> str:
    path = urlparse(url).path or "/"
    if path != "/":
        path = path.rstrip("/") or "/"
    return path


def matches_glob(path: str, pattern: str) -> bool:
    candidates = {path, path + "/" if path != "/" else path}
    patterns = {pattern, pattern.lstrip("/"), "/" + pattern.lstrip("/")}
    for p in candidates:
        for g in patterns:
            if fnmatch.fnmatch(p, g) or fnmatch.fnmatch(p.lstrip("/"), g.lstrip("/")):
                return True
    return False


def denied_prefix(path: str, prefix: str) -> bool:
    p = prefix.rstrip("/")
    return path == p or path.startswith(p + "/")


def should_queue(
    url: str,
    *,
    include_paths: tuple[str, ...] = (),
    exclude_paths: tuple[str, ...] = (),
    only_home: bool = False,
    apply_deny_list: bool = True,
) -> bool:
    path = normalized_path(url)
    query = parse_qs(urlparse(url).query)

    included = False
    if include_paths:
        if not any(matches_glob(path, g) for g in include_paths):
            return False
        included = True
    if any(matches_glob(path, g) for g in exclude_paths):
        return False
    if included or not apply_deny_list:
        return True
    if path in ("", "/") and not only_home:
        return False
    if any(denied_prefix(path, p) for p in DENY_PREFIXES):
        return False
    if _PAGE.fullmatch(path):
        return False
    keys = set(query)
    if keys & {"replytocom", "s"} or query.get("preview") == ["true"] or "paged" in keys:
        return False
    if "/attachment/" in path or "attachment_id" in query:
        return False
    if _ASSET.search(path):
        return False
    return True
