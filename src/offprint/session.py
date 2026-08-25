"""Shared HTTP session: one client + robots cache (+ optional browser later)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from offprint.fetch import FetchClient
from offprint.robots import RobotsCache


@dataclass
class RunSession:
    """One per extract_site run; extract_url may allocate an ephemeral session."""

    client: FetchClient
    robots: RobotsCache
    browser: object | None = field(default=None)

    async def aclose(self) -> None:
        if self.browser is not None:
            close = getattr(self.browser, "close", None)
            if close is not None:
                await close()
            self.browser = None
        await self.client.aclose()


async def open_session(*, ignore_robots: bool = False, **fetch_kwargs: Any) -> RunSession:
    client = FetchClient(**fetch_kwargs)
    robots = RobotsCache(client, ignore=ignore_robots)
    return RunSession(client=client, robots=robots)
