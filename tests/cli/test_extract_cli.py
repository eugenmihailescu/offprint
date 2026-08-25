"""CLI extract, schema, argv sugar, and exit codes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from offprint.cli import main, preprocess_argv
from offprint.errors import BlockedUrlError, NotArticleError
from offprint.model import Article, Provenance


def _article() -> Article:
    return Article(
        origin="https://example.com",
        canonicalUrl="https://example.com/p/fm",
        title="The FM transmitter",
        html="<p>Hello</p>",
        text="Hello",
        provenance=Provenance(
            method="html-article",
            fetchedAt="2026-08-25T12:00:00Z",
            finalUrl="https://example.com/p/fm",
            extractorVersion="offprint/0.1.0",
        ),
    )


def test_preprocess_url_becomes_extract() -> None:
    assert preprocess_argv(["https://old.blog/foo/"])[0] == "extract"
    assert preprocess_argv(["https://old.blog/foo/", "--pretty"])[0] == "extract"
    assert preprocess_argv(["--out", "a.json", "https://old.blog/foo/"])[0] == "extract"


def test_preprocess_origin_becomes_site() -> None:
    assert preprocess_argv(["--origin", "https://old.blog", "--out", "c.jsonl"])[0] == "site"
    assert preprocess_argv(["--urls-file", "urls.txt", "--out", "c.jsonl"])[0] == "site"


def test_preprocess_leaves_verbs() -> None:
    assert preprocess_argv(["extract", "https://x/"])[0] == "extract"
    assert preprocess_argv(["schema", "--run"])[0] == "schema"
    assert preprocess_argv(["version"]) == ["version"]


def test_schema_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["schema"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["$id"].endswith("offprint-article.v1.json")
    assert data["title"] == "Offprint Article"


def test_schema_run(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["schema", "--run"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["$id"].endswith("offprint-run.v1.json")


def test_extract_stdout_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: dict[str, object] = {}

    def fake(url: str, options=None):
        seen["url"] = url
        seen["options"] = options
        return _article()

    monkeypatch.setattr("offprint.cli.extract_url", fake)
    assert main(["extract", "https://example.com/p/fm", "--pretty"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["kind"] == "offprint-article"
    assert out["title"] == "The FM transmitter"
    assert seen["url"] == "https://example.com/p/fm"


def test_extract_from_bare_url(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("offprint.cli.extract_url", lambda url, options=None: _article())
    assert main(["https://example.com/p/fm", "--pretty"]) == 0
    assert json.loads(capsys.readouterr().out)["canonicalUrl"] == "https://example.com/p/fm"


def test_extract_out_and_save_html(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: dict[str, object] = {}

    def fake(url: str, options=None):
        seen["options"] = options
        return _article()

    monkeypatch.setattr("offprint.cli.extract_url", fake)
    dest = tmp_path / "out" / "article.json"
    html_dir = tmp_path / "html"
    argv = [
        "extract",
        "https://example.com/p/fm",
        "--out",
        str(dest),
        "--save-html",
        str(html_dir),
    ]
    assert main(argv) == 0
    assert dest.is_file()
    assert json.loads(dest.read_text(encoding="utf-8"))["title"] == "The FM transmitter"
    assert capsys.readouterr().out == ""
    opts = seen["options"]
    assert opts.save_html_dir == html_dir


def test_extract_error_exit_codes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "offprint.cli.extract_url",
        lambda url, options=None: (_ for _ in ()).throw(
            BlockedUrlError("nope", url=url),
        ),
    )
    assert main(["extract", "http://127.0.0.1/"]) == 3
    monkeypatch.setattr(
        "offprint.cli.extract_url",
        lambda url, options=None: (_ for _ in ()).throw(NotArticleError("empty", url=url)),
    )
    assert main(["extract", "https://example.com/x"]) == 7


def test_extract_missing_url() -> None:
    assert main(["extract"]) == 2
