"""Offprint: extract an article from a public URL or site as JSON."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version

from offprint.errors import OffprintError
from offprint.fetch import FetchResult
from offprint.model import Article, RunManifest
from offprint.pipeline import ExtractOptions, extract_url, extract_url_async

try:
    __version__ = pkg_version("offprint")
except PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "Article",
    "ExtractOptions",
    "FetchResult",
    "OffprintError",
    "RunManifest",
    "extract_url",
    "extract_url_async",
    "__version__",
]
