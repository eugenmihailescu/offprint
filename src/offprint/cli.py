"""Argparse entry: extract, schema, version. Site mode is PR 6."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from offprint import __version__
from offprint.constants import (
    DEFAULT_CONNECT_TIMEOUT_SEC,
    DEFAULT_MAX_BYTES,
    DEFAULT_MAX_REDIRECTS,
    DEFAULT_MIN_TEXT_CHARS,
    DEFAULT_READ_TIMEOUT_SEC,
)
from offprint.errors import OffprintError, UsageError
from offprint.log import setup_logging
from offprint.pipeline import ExtractOptions, extract_url
from offprint.schema import dump_article_schema, dump_run_schema, schema_to_json

log = logging.getLogger("offprint")

_VALUE_FLAGS = frozenset(
    {
        "--out",
        "--timeout",
        "--connect-timeout",
        "--max-bytes",
        "--max-redirects",
        "--user-agent",
        "--save-html",
        "--min-text-chars",
        "--download-media",
        "--log-format",
        "--origin",
        "--urls-file",
        "--out-dir",
        "--concurrency",
        "--delay",
        "--limit",
        "--max-urls",
        "--include-path",
        "--exclude-path",
    }
)
_VERBS = frozenset({"extract", "site", "schema", "version"})


def preprocess_argv(argv: list[str]) -> list[str]:
    """Insert extract/site so `offprint URL` and `offprint --origin …` work."""
    if not argv:
        return argv
    if argv[0] in _VERBS or argv[0] in {"-h", "--help", "--version"}:
        return argv
    if _has_positional(argv):
        return ["extract", *argv]
    joined = " ".join(argv)
    if "--origin" in joined or "--urls-file" in joined:
        return ["site", *argv]
    return argv


def _has_positional(argv: list[str]) -> bool:
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok.startswith("-"):
            key = tok.split("=", 1)[0]
            if key in _VALUE_FLAGS and "=" not in tok:
                i += 2
                continue
            i += 1
            continue
        return True
    return False


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="offprint",
        description=(
            "Extract the article from a URL or a whole site. Emits structured JSON — not CMS rows."
        ),
    )
    parser.add_argument("--version", action="version", version=f"offprint {__version__}")
    sub = parser.add_subparsers(dest="cmd")

    extract = sub.add_parser("extract", help="extract one URL")
    extract.add_argument("url", help="article URL")
    _add_shared(extract)

    schema = sub.add_parser("schema", help="print JSON Schema")
    schema.add_argument(
        "--run",
        action="store_true",
        help="emit offprint-run schema instead of offprint-article",
    )

    site = sub.add_parser("site", help="extract a whole origin (not in this release)")
    site.add_argument("--origin", default=None)
    site.add_argument("--urls-file", default=None)
    _add_shared(site)
    return parser


def _add_shared(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--out", default=None, dest="out_path")
    parser.add_argument("--pretty", action="store_true")
    parser.add_argument("--ignore-robots", action="store_true")
    parser.add_argument("--timeout", type=float, default=DEFAULT_READ_TIMEOUT_SEC)
    parser.add_argument("--connect-timeout", type=float, default=DEFAULT_CONNECT_TIMEOUT_SEC)
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    parser.add_argument("--max-redirects", type=int, default=DEFAULT_MAX_REDIRECTS)
    parser.add_argument("--user-agent", default=None)
    parser.add_argument("--save-html", type=Path, default=None)
    browser = parser.add_mutually_exclusive_group()
    browser.add_argument("--browser", action="store_true")
    browser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--min-text-chars", type=int, default=DEFAULT_MIN_TEXT_CHARS)
    parser.add_argument("--probe-media", action="store_true")
    parser.add_argument("--download-media", type=Path, default=None)
    parser.add_argument("-v", action="count", default=0, dest="verbose")
    parser.add_argument("-q", "--quiet", action="store_true")
    parser.add_argument("--log-format", choices=("text", "json"), default="text")


def main(argv: Sequence[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    parser = _parser()
    if not raw:
        parser.print_help(sys.stdout)
        return 0
    if raw == ["version"]:
        print(f"offprint {__version__}")
        return 0
    cooked = preprocess_argv(raw)
    try:
        ns = parser.parse_args(cooked)
    except SystemExit as exc:
        code = exc.code
        if code in (0, None):
            return 0
        return code if isinstance(code, int) else 1
    if not ns.cmd:
        parser.print_usage(sys.stderr)
        return 2
    setup_logging(
        verbose=getattr(ns, "verbose", 0) or 0,
        quiet=getattr(ns, "quiet", False),
        fmt=getattr(ns, "log_format", "text"),
    )
    try:
        if ns.cmd == "schema":
            return _cmd_schema(ns)
        if ns.cmd == "site":
            raise UsageError("site mode is not implemented yet")
        if ns.cmd == "extract":
            return _cmd_extract(ns)
        parser.print_usage(sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
    except OffprintError as exc:
        log.error(exc.message, extra={"url": exc.url, "code": exc.code})
        return exc.exit_code


def _cmd_schema(ns: argparse.Namespace) -> int:
    schema = dump_run_schema() if ns.run else dump_article_schema()
    sys.stdout.write(schema_to_json(schema))
    return 0


def _cmd_extract(ns: argparse.Namespace) -> int:
    ua = ns.user_agent or os.environ.get("OFFPRINT_USER_AGENT") or None
    if ua is not None and not str(ua).strip():
        ua = None
    browser: bool | None
    if ns.browser:
        browser = True
    elif ns.no_browser:
        browser = False
    else:
        browser = None
    options = ExtractOptions(
        ignore_robots=ns.ignore_robots,
        timeout=ns.timeout,
        connect_timeout=ns.connect_timeout,
        max_bytes=ns.max_bytes,
        max_redirects=ns.max_redirects,
        user_agent=ua,
        save_html_dir=ns.save_html,
        browser=browser,
        min_text_chars=ns.min_text_chars,
        probe_media=ns.probe_media,
        download_media_dir=ns.download_media,
    )
    article = extract_url(ns.url, options)
    pretty = ns.pretty or (ns.out_path is None and sys.stdout.isatty())
    payload = article.model_dump(mode="json", exclude_none=False)
    text = json.dumps(payload, indent=2 if pretty else None, ensure_ascii=False) + "\n"
    if ns.out_path:
        path = Path(ns.out_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0
