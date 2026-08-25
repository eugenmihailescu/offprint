"""Argparse entry point. Extract/site modes are stubs until later PRs."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from offprint import __version__


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="offprint",
        description=(
            "Extract the article from a URL or a whole site. Emits structured JSON — not CMS rows."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"offprint {__version__}",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    parser = _parser()
    if not args:
        parser.print_help(sys.stdout)
        return 0
    if args == ["version"]:
        print(f"offprint {__version__}")
        return 0
    try:
        parser.parse_args(args)
    except SystemExit as exc:
        code = exc.code
        if code in (0, None):
            return 0
        return code if isinstance(code, int) else 1
    parser.print_help(sys.stdout)
    return 0
