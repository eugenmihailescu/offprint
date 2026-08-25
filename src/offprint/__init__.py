"""Offprint: extract an article from a public URL or site as JSON."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version

try:
    __version__ = pkg_version("offprint")
except PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = ["__version__"]
