"""Stderr progress for site runs. Disabled unless ``--progress``. Never writes stdout."""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from typing import TextIO


def format_duration(seconds: float) -> str:
    if seconds < 0 or seconds != seconds or seconds == float("inf"):
        return "?"
    total = int(seconds + 0.5)
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h{minutes:02d}m"
    if minutes:
        return f"{minutes}m{secs:02d}s"
    return f"{secs}s"


def extract_eta(*, elapsed: float, paid: int, remaining: int) -> str:
    """ETA from URLs that actually cost fetch time (not resume / not-attempted)."""
    if remaining <= 0:
        return "0s"
    if paid <= 0 or elapsed <= 0:
        return "?"
    return format_duration(remaining * (elapsed / paid))


class Progress:
    """TTY: rewrite one stderr line. Pipes/tests: one line per update."""

    def __init__(
        self,
        *,
        enabled: bool = False,
        stream: TextIO | None = None,
        tty: bool | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        min_interval: float = 0.25,
    ) -> None:
        self.enabled = enabled
        self.stream = stream if stream is not None else sys.stderr
        self.tty = self.stream.isatty() if tty is None else tty
        self._now = monotonic
        self._min_interval = min_interval
        self._extract_started: float | None = None
        self._last_write = 0.0
        self._last_width = 0
        self._dirty = False

    def discover(
        self,
        phase: str,
        *,
        sitemaps: int = 0,
        feeds: int = 0,
        locs: int = 0,
        pages: int | None = None,
    ) -> None:
        if not self.enabled:
            return
        parts = [
            f"discover {phase}",
            f"sitemaps={sitemaps}",
            f"feeds={feeds}",
            f"locs={locs}",
        ]
        if pages is not None:
            parts.append(f"pages={pages}")
        self._emit(" ".join(parts), force=True)

    def extract_begin(self, queued: int) -> None:
        if not self.enabled:
            return
        self._extract_started = self._now()
        self.extract_tick(
            extracted=0,
            failed=0,
            skipped=0,
            resumed=0,
            not_attempted=0,
            queued=queued,
            force=True,
        )

    def extract_tick(
        self,
        *,
        extracted: int,
        failed: int,
        skipped: int,
        resumed: int,
        not_attempted: int,
        queued: int,
        force: bool = False,
    ) -> None:
        if not self.enabled:
            return
        started = self._extract_started
        elapsed = 0.0 if started is None else max(0.0, self._now() - started)
        done = extracted + failed + skipped + resumed + not_attempted
        remaining = max(0, queued - done)
        paid = extracted + failed + skipped
        eta = extract_eta(elapsed=elapsed, paid=paid, remaining=remaining)
        line = (
            f"extract {done}/{queued} extracted={extracted} failed={failed} "
            f"skipped={skipped} resumed={resumed} elapsed={format_duration(elapsed)} eta={eta}"
        )
        self._emit(line, force=force or remaining == 0)

    def close(self) -> None:
        if not self.enabled or not self._dirty:
            return
        if self.tty:
            self.stream.write("\n")
            self.stream.flush()
        self._dirty = False

    def _emit(self, line: str, *, force: bool) -> None:
        now = self._now()
        if not force and (now - self._last_write) < self._min_interval:
            return
        self._last_write = now
        if self.tty:
            padded = line + " " * max(0, self._last_width - len(line))
            self.stream.write("\r" + padded)
            self._last_width = max(self._last_width, len(line))
        else:
            self.stream.write(line + "\n")
        self.stream.flush()
        self._dirty = True
