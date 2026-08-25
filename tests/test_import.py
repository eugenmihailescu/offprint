"""Smoke tests for the installed package (PR 1 scaffold)."""

from __future__ import annotations

import offprint
from offprint.cli import main
from offprint.constants import DEFAULT_MAX_BYTES, default_user_agent


def test_version_from_metadata() -> None:
    assert offprint.__version__
    assert offprint.__version__ != "0.0.0"


def test_cli_help_no_args() -> None:
    assert main([]) == 0


def test_cli_help_flag() -> None:
    assert main(["--help"]) == 0


def test_cli_version_flag() -> None:
    assert main(["--version"]) == 0


def test_cli_version_verb() -> None:
    assert main(["version"]) == 0


def test_cli_unknown_exits_usage() -> None:
    assert main(["--not-a-real-flag"]) == 2


def test_constants_and_ua() -> None:
    assert DEFAULT_MAX_BYTES == 10 * 1024 * 1024
    ua = default_user_agent(offprint.__version__)
    assert ua.startswith("Offprint/")
    assert "github.com/eugenmihailescu/offprint" in ua
