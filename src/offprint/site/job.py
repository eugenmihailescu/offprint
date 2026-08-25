"""Site extract: polite workers + single JSONL writer."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import urlparse

from offprint.constants import (
    BROWSER_CONCURRENCY_HARD_CAP,
    CONCURRENCY_HARD_CAP,
    DEFAULT_BROWSER_CONCURRENCY,
    DEFAULT_CONCURRENCY,
    DEFAULT_CONNECT_TIMEOUT_SEC,
    DEFAULT_DELAY_SEC,
    DEFAULT_MAX_BYTES,
    DEFAULT_MAX_REDIRECTS,
    DEFAULT_MAX_URLS,
    DEFAULT_MIN_TEXT_CHARS,
    DEFAULT_READ_TIMEOUT_SEC,
)
from offprint.discover import discover, read_urls_file
from offprint.errors import (
    FetchError,
    NotArticleError,
    OffprintError,
    RobotsDeniedError,
    UsageError,
)
from offprint.extract.browser import ensure_browser, require_playwright
from offprint.extract.feeds_match import FeedItem
from offprint.model import Article, RunManifest
from offprint.pipeline import ExtractOptions, extract_url_async
from offprint.session import RunSession, open_session
from offprint.site.manifest import (
    RESULT_EXIT,
    decide_result,
    empty_stats,
    new_config,
    new_failure,
    utc_now,
    write_manifest,
)
from offprint.site.resume import (
    ResumeState,
    article_keys,
    load_state,
    state_path,
    write_state,
)
from offprint.urls import canonical_key, parse_origin, same_site_family

log = logging.getLogger("offprint.site")

_FAIL_CODES = frozenset(
    {"ssrf_blocked", "http_4xx", "http_5xx", "network", "too_large", "invalid_document"}
)


@dataclass(frozen=True)
class SiteOptions:
    origin: str
    out_path: Path
    out_dir: Path | None = None
    concurrency: int | None = None
    delay: float = DEFAULT_DELAY_SEC
    limit: int | None = None
    max_urls: int = DEFAULT_MAX_URLS
    include_paths: tuple[str, ...] = ()
    exclude_paths: tuple[str, ...] = ()
    resume: bool = False
    overwrite: bool = False
    no_crawl: bool = False
    urls_file: Path | None = None
    ignore_robots: bool = False
    timeout: float = DEFAULT_READ_TIMEOUT_SEC
    connect_timeout: float = DEFAULT_CONNECT_TIMEOUT_SEC
    max_bytes: int = DEFAULT_MAX_BYTES
    max_redirects: int = DEFAULT_MAX_REDIRECTS
    user_agent: str | None = None
    save_html_dir: Path | None = None
    browser: bool | None = None
    min_text_chars: int = DEFAULT_MIN_TEXT_CHARS
    probe_media: bool = False
    download_media_dir: Path | None = None

    def capped_concurrency(self) -> int:
        if self.browser:
            n = DEFAULT_BROWSER_CONCURRENCY if self.concurrency is None else self.concurrency
            return min(max(1, n), BROWSER_CONCURRENCY_HARD_CAP)
        n = DEFAULT_CONCURRENCY if self.concurrency is None else self.concurrency
        return min(max(1, n), CONCURRENCY_HARD_CAP)

    def to_extract_options(
        self,
        feed_index: Mapping[str, FeedItem],
        session: RunSession,
    ) -> ExtractOptions:
        return ExtractOptions(
            origin=self.origin,
            ignore_robots=self.ignore_robots,
            timeout=self.timeout,
            connect_timeout=self.connect_timeout,
            max_bytes=self.max_bytes,
            max_redirects=self.max_redirects,
            user_agent=self.user_agent,
            save_html_dir=self.save_html_dir,
            browser=self.browser,
            min_text_chars=self.min_text_chars,
            probe_media=self.probe_media,
            download_media_dir=self.download_media_dir,
            feed_index=feed_index,
            session=session,
        )


class _Pace:
    def __init__(self, delay: float, session: RunSession) -> None:
        self.delay = delay
        self.session = session
        self._next: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def wait(self, url: str) -> None:
        host = urlparse(url).hostname or ""
        interval = self.delay
        if not self.session.robots.ignore:
            raw = self.session.robots.crawl_interval(url, self.session.client.user_agent)
            interval = max(interval, self.session.robots.clamp_interval(raw))
        lock = self._locks.setdefault(host, asyncio.Lock())
        async with lock:
            loop = asyncio.get_running_loop()
            now = loop.time()
            slot = max(now, self._next.get(host, now))
            self._next[host] = slot + interval
        delay = slot - asyncio.get_running_loop().time()
        if delay > 0:
            await asyncio.sleep(delay)


def extract_site(options: SiteOptions) -> RunManifest:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(extract_site_async(options))
    raise UsageError("use extract_site_async inside a running event loop")


async def extract_site_async(options: SiteOptions) -> RunManifest:
    origin = parse_origin(options.origin) if options.origin else ""
    if options.urls_file is None and not origin:
        raise UsageError("site mode requires --origin or --urls-file")
    out_path = options.out_path
    if options.resume and options.overwrite:
        raise UsageError("use either --resume or --overwrite, not both")
    if out_path.exists() and not options.overwrite and not options.resume:
        raise UsageError(f"--out already exists (pass --overwrite or --resume): {out_path}")
    if options.urls_file is not None and not origin:
        listed = read_urls_file(options.urls_file, max_urls=options.max_urls)
        if not listed:
            raise UsageError("urls-file contained no URLs and --origin is missing")
        origin = parse_origin(listed[0])
    options = replace(options, origin=origin)

    out_dir = options.out_dir or out_path.parent
    state_file = state_path(out_dir)
    if options.resume:
        resume_state = load_state(state_file)
    else:
        resume_state = ResumeState()
        write_state(state_file, resume_state)
    started = utc_now()
    own = True
    session = await open_session(
        ignore_robots=options.ignore_robots,
        timeout=options.timeout,
        connect_timeout=options.connect_timeout,
        max_bytes=options.max_bytes,
        max_redirects=options.max_redirects,
        user_agent=options.user_agent,
    )
    if options.browser is True:
        require_playwright()
        await ensure_browser(session)
    interrupted = False
    stats = empty_stats()
    failures: list = []
    skipped_sample: list = []
    queued_skips = 0
    failures_truncated = False
    try:
        disc = await discover(
            origin,
            session,
            max_urls=options.max_urls,
            include_paths=options.include_paths,
            exclude_paths=options.exclude_paths,
            no_crawl=options.no_crawl,
            urls_file=options.urls_file,
            apply_deny_list=options.urls_file is None,
        )
        stats.discovered = disc.discovered_count
        stats.queued = len(disc.urls)
        stats.skipped = len(disc.skipped)
        skipped_sample = [new_failure(s.url, s.code) for s in disc.skipped[:50]]
        extract_opts = options.to_extract_options(disc.feed_index, session)
        n = options.capped_concurrency()
        pace = _Pace(options.delay, session)
        url_q: asyncio.Queue[str | None] = asyncio.Queue()
        result_q: asyncio.Queue[tuple] = asyncio.Queue()
        gate = asyncio.Lock()
        in_flight: set[str] = set()
        for url in disc.urls:
            url_q.put_nowait(url)
        for _ in range(n):
            url_q.put_nowait(None)
        extracted_holder = {"n": 0}
        limit = options.limit

        async def worker() -> None:
            while True:
                url = await url_q.get()
                try:
                    key: str | None = None
                    if url is None:
                        return
                    if limit is not None and extracted_holder["n"] >= limit:
                        await result_q.put(("not_attempted", url, None, None))
                        continue
                    try:
                        key = canonical_key(url)
                    except UsageError as exc:
                        await result_q.put(("fail", url, exc, None))
                        continue
                    async with gate:
                        if key in resume_state.done:
                            await result_q.put(("resume", url, None, None))
                            continue
                        if key in in_flight:
                            await result_q.put(("skip", url, "duplicate", None))
                            continue
                        in_flight.add(key)
                    await pace.wait(url)
                    try:
                        article = await extract_url_async(url, extract_opts)
                    except RobotsDeniedError as exc:
                        await result_q.put(("skip", url, exc, key))
                        continue
                    except NotArticleError as exc:
                        await result_q.put(("skip", url, exc, key))
                        continue
                    except OffprintError as exc:
                        await result_q.put(("fail", url, exc, key))
                        continue
                    if not same_site_family(article.provenance.finalUrl, origin):
                        await result_q.put(("skip", url, "off_origin", key))
                        continue
                    extracted_holder["n"] += 1
                    await result_q.put(("ok", article, url, key))
                except Exception as exc:
                    log.exception("worker failed for %s", url)
                    await result_q.put(
                        (
                            "fail",
                            url,
                            FetchError(str(exc) or "worker error", url=url),
                            key,
                        )
                    )
                finally:
                    url_q.task_done()

        async def writer() -> None:
            nonlocal queued_skips, failures_truncated
            out_path.parent.mkdir(parents=True, exist_ok=True)
            mode = "a" if options.resume else "w"
            with out_path.open(mode, encoding="utf-8") as fh:
                pending = stats.queued
                while pending > 0:
                    kind, payload, extra, key = await result_q.get()
                    pending -= 1
                    if kind == "ok":
                        article: Article = payload
                        requested = extra if isinstance(extra, str) else article.canonicalUrl
                        fh.write(
                            json.dumps(
                                article.model_dump(mode="json", exclude_none=False),
                                ensure_ascii=False,
                            )
                            + "\n"
                        )
                        fh.flush()
                        async with gate:
                            resume_state.done.update(article_keys(article, requested))
                            if key:
                                in_flight.discard(key)
                            write_state(state_file, resume_state)
                        stats.extracted += 1
                    else:
                        if key:
                            async with gate:
                                in_flight.discard(key)
                        if kind == "resume":
                            stats.resumed += 1
                        elif kind == "skip":
                            code = extra.code if isinstance(extra, OffprintError) else str(extra)
                            queued_skips += 1
                            stats.skipped += 1
                            if len(skipped_sample) < 50:
                                skipped_sample.append(
                                    new_failure(
                                        payload,
                                        code,
                                        getattr(extra, "message", "") or "",
                                    )
                                )
                        elif kind == "not_attempted":
                            stats.notAttempted += 1
                        elif kind == "fail":
                            stats.failed += 1
                            err: OffprintError = extra
                            if len(failures) < 200:
                                failures.append(new_failure(payload, err.code, err.message))
                            else:
                                failures_truncated = True
                    log.info(
                        "extracted=%s failed=%s skipped=%s queued=%s resumed=%s",
                        stats.extracted,
                        stats.failed,
                        stats.skipped,
                        stats.queued,
                        stats.resumed,
                    )

        workers = [asyncio.create_task(worker()) for _ in range(n)]
        writer_task: asyncio.Task | None = None
        if stats.queued:
            writer_task = asyncio.create_task(writer())
        try:
            await url_q.join()
            if writer_task is not None:
                await writer_task
        except KeyboardInterrupt:
            interrupted = True
            for task in workers:
                task.cancel()
            if writer_task is not None:
                writer_task.cancel()
        await asyncio.gather(*workers, return_exceptions=True)
    finally:
        if own:
            await session.aclose()

    result = decide_result(stats, queued_skips=queued_skips, interrupted=interrupted)
    manifest = RunManifest(
        origin=origin,
        startedAt=started,
        finishedAt=utc_now(),
        outPath=str(out_path),
        result=result,
        stats=stats,
        config=new_config(
            concurrency=options.capped_concurrency(),
            delay=options.delay,
            ignore_robots=options.ignore_robots,
            browser=options.browser,
            max_bytes=options.max_bytes,
        ),
        failures=failures,
        failuresTruncated=failures_truncated,
        skippedSample=skipped_sample,
    )
    write_manifest(out_dir / "manifest.json", manifest)
    return manifest


def site_exit_code(manifest: RunManifest) -> int:
    return RESULT_EXIT[manifest.result]
