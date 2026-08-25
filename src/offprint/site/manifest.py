"""Map run stats to offprint-run result + CLI exit code."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from offprint.model import RunConfig, RunFailure, RunManifest, RunResult, RunStats

RESULT_EXIT: dict[RunResult, int] = {
    "ok": 0,
    "partial": 10,
    "empty_queue": 10,
    "skipped_all": 10,
    "interrupted": 130,
}


def decide_result(
    stats: RunStats,
    *,
    queued_skips: int,
    interrupted: bool,
) -> RunResult:
    if interrupted:
        return "interrupted"
    if stats.failed > 0:
        return "partial"
    if stats.extracted == 0 and stats.queued == 0:
        return "empty_queue"
    if stats.extracted == 0 and queued_skips > 0:
        return "skipped_all"
    if stats.failed == 0 and (
        stats.extracted >= 1
        or (
            queued_skips == 0
            and stats.extracted + stats.resumed >= 1
            and stats.extracted + stats.resumed + stats.notAttempted == stats.queued
        )
    ):
        return "ok"
    if stats.extracted == 0 and stats.failed == 0:
        return "empty_queue"
    return "ok"


def write_manifest(path: Path, manifest: RunManifest) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def browser_mode(flag: bool | None) -> str:
    if flag is True:
        return "on"
    if flag is False:
        return "off"
    return "fallback"


def empty_stats() -> RunStats:
    return RunStats()


def new_config(
    *,
    concurrency: int,
    delay: float,
    ignore_robots: bool,
    browser: bool | None,
    max_bytes: int,
) -> RunConfig:
    return RunConfig(
        concurrency=concurrency,
        delaySec=delay,
        ignoreRobots=ignore_robots,
        browser=browser_mode(browser),  # type: ignore[arg-type]
        maxBytes=max_bytes,
    )


def new_failure(url: str, code: str, message: str = "") -> RunFailure:
    return RunFailure(url=url, code=code, message=message)
