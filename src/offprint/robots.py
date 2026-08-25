"""protego robots.txt cache. Missing files allow. Fetch goes through FetchClient."""

from __future__ import annotations

import logging
from urllib.parse import urljoin, urlparse

from protego import Protego

from offprint.constants import ROBOTS_DELAY_CLAMP_SEC
from offprint.errors import HttpError, RobotsDeniedError, SizeError
from offprint.fetch import FetchClient
from offprint.urls import parse_origin

log = logging.getLogger("offprint.robots")


class RobotsCache:
    """One protego document per origin host, fetched via FetchClient."""

    def __init__(self, client: FetchClient, *, ignore: bool = False) -> None:
        self._client = client
        self.ignore = ignore
        self._cache: dict[str, Protego | None] = {}
        self._warned_ignore = False

    async def allow(self, url: str, ua: str) -> bool:
        if self.ignore:
            self._warn_ignore(url)
            return True
        robot = await self._load(url)
        if robot is None:
            return True
        if robot.can_fetch(url, ua):
            return True
        if ua != "Offprint" and robot.can_fetch(url, "Offprint"):
            return True
        return False

    async def require(self, url: str, ua: str) -> None:
        if not await self.allow(url, ua):
            raise RobotsDeniedError("robots.txt disallows this URL", url=url)

    def crawl_interval(self, url: str, ua: str) -> float:
        """Unclamped delay from crawl-delay / request-rate. 0 if none or ignore."""
        if self.ignore:
            return 0.0
        origin = _robots_origin(url)
        robot = self._cache.get(origin)
        if robot is None:
            return 0.0
        interval = 0.0
        delay = robot.crawl_delay(ua)
        if delay is None:
            delay = robot.crawl_delay("Offprint")
        if delay is not None:
            interval = max(interval, float(delay))
        rate = robot.request_rate(ua) or robot.request_rate("Offprint")
        if rate is not None and getattr(rate, "requests", 0):
            seconds = float(getattr(rate, "seconds", 0) or 0)
            if seconds > 0:
                interval = max(interval, seconds / float(rate.requests))
        return interval

    def sitemap_urls(self, url: str) -> list[str]:
        origin = _robots_origin(url)
        robot = self._cache.get(origin)
        if robot is None:
            return []
        return [str(s).strip() for s in robot.sitemaps if str(s).strip()]

    def clamp_interval(self, interval: float) -> float:
        if interval > ROBOTS_DELAY_CLAMP_SEC:
            log.warning(
                "clamping robots crawl-delay/request-rate from %ss to %ss",
                interval,
                ROBOTS_DELAY_CLAMP_SEC,
            )
            return ROBOTS_DELAY_CLAMP_SEC
        return interval

    async def _load(self, url: str) -> Protego | None:
        origin = _robots_origin(url)
        if origin in self._cache:
            return self._cache[origin]
        robots_url = urljoin(origin + "/", "robots.txt")
        try:
            result = await self._client.get(robots_url)
        except HttpError:
            self._cache[origin] = None
            return None
        except SizeError:
            raise
        body = result.body.decode("utf-8", errors="replace")
        parsed = Protego.parse(body)
        self._cache[origin] = parsed
        return parsed

    def _warn_ignore(self, url: str) -> None:
        if self._warned_ignore:
            return
        self._warned_ignore = True
        host = urlparse(url).hostname or url
        log.warning("ignoring robots.txt for operator-owned origin %s", host)


def _robots_origin(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme in ("http", "https") and parsed.hostname:
        return parse_origin(url)
    return parse_origin(url)
