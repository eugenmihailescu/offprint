"""HTML overlay extractors. Playwright lives in ``extract.browser`` (optional extra)."""

from offprint.extract.feeds_match import FeedItem
from offprint.extract.overlay import OverlayResult, overlay
from offprint.extract.sanitize import sanitize

__all__ = ["FeedItem", "OverlayResult", "overlay", "sanitize"]
