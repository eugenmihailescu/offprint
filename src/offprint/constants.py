"""Fetch and document limits. Version is not stored here — use ``offprint.__version__``."""

from __future__ import annotations

REPO_URL = "https://github.com/eugenmihailescu/offprint"

DEFAULT_CONNECT_TIMEOUT_SEC = 10.0
DEFAULT_READ_TIMEOUT_SEC = 20.0
DEFAULT_POOL_TIMEOUT_SEC = 10.0
TIMEOUT_HARD_CAP_SEC = 120.0

DEFAULT_MAX_REDIRECTS = 5
MAX_REDIRECTS_HARD_CAP = 10

DEFAULT_MAX_BYTES = 10 * 1024 * 1024
MAX_BYTES_HARD_CAP = 50 * 1024 * 1024

DEFAULT_CONCURRENCY = 4
DEFAULT_BROWSER_CONCURRENCY = 2
CONCURRENCY_HARD_CAP = 16
BROWSER_CONCURRENCY_HARD_CAP = 4

DEFAULT_DELAY_SEC = 0.5
ROBOTS_DELAY_CLAMP_SEC = 10.0

MAX_SITEMAPS = 50
DEFAULT_MAX_URLS = 50_000
CRAWL_MAX_PAGES = 500
CRAWL_MAX_DEPTH = 3

MEDIA_DOWNLOAD_MAX_BYTES = 20 * 1024 * 1024
MEDIA_PROBE_TIMEOUT_SEC = 5.0
MEDIA_PROBE_MAX_BYTES = 64
ARTICLE_HTML_MAX_CHARS = 5_000_000
URL_MAX_LENGTH = 2048
MEDIA_SRC_MAX_LENGTH = 4096
TITLE_MAX_CHARS = 500
EXCERPT_MAX_CHARS = 4000
TEXT_MAX_CHARS = 1_000_000
DEFAULT_MIN_TEXT_CHARS = 200

ACCEPT_HEADER = (
    "text/html,application/xhtml+xml,"
    "application/rss+xml,application/atom+xml,application/feed+json,"
    "application/json;q=0.5,application/xml;q=0.9,text/xml;q=0.8,*/*;q=0.1"
)

TRACKING_PARAMS: frozenset[str] = frozenset(
    {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "utm_id",
        "utm_reader",
        "gclid",
        "gbraid",
        "wbraid",
        "fbclid",
        "gclsrc",
        "mc_cid",
        "mc_eid",
        "igshid",
        "_ga",
        "_gl",
        "msclkid",
        "twclid",
        "yclid",
        "dclid",
        "li_fat_id",
        "wickedid",
        "ncid",
        "srsltid",
        "ref_src",
        "ref_url",
        "share",
        "amp",
    }
)
TRACKING_QUERY_PARAMS = TRACKING_PARAMS


def default_user_agent(version: str) -> str:
    """UA uses the installed package version, not a second constant."""
    return f"Offprint/{version} (+{REPO_URL}; article-extractor)"
