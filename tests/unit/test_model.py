"""Dump/load, extra-key stripping, dates, errors, and schema drift."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from offprint import Article, OffprintError, RunManifest, __version__
from offprint.dates import parse_datetime
from offprint.errors import (
    BlockedUrlError,
    FetchError,
    HttpError,
    NotArticleError,
    RobotsDeniedError,
    SchemaError,
    SizeError,
    UsageError,
)
from offprint.model import Media, Provenance, RunConfig, RunFailure, RunStats
from offprint.schema import dump_article_schema, dump_run_schema, schema_to_json

REPO = Path(__file__).resolve().parents[2]


def _provenance(**overrides: object) -> Provenance:
    data: dict[str, object] = {
        "method": "html-article",
        "methodChain": ["jsonld", "html-article"],
        "fetchedAt": "2026-08-25T12:00:00Z",
        "finalUrl": "https://old.blog/2020/foo/",
        "httpStatus": 200,
        "contentType": "text/html; charset=UTF-8",
        "bytes": 18432,
        "redirects": [],
        "extractorVersion": f"offprint/{__version__}",
        "rawHtmlSha256": None,
        "rawHtmlPath": None,
        "robotsIgnored": False,
        "truncated": [],
    }
    data.update(overrides)
    return Provenance.model_validate(data)


def _article(**overrides: object) -> Article:
    data: dict[str, object] = {
        "kind": "offprint-article",
        "version": 1,
        "origin": "https://old.blog",
        "canonicalUrl": "https://old.blog/2020/foo/",
        "discoveredUrls": [
            "https://old.blog/2020/foo/",
            "https://old.blog/2020/foo",
        ],
        "title": "Foo",
        "publishedAt": "2020-03-01T00:00:00Z",
        "updatedAt": None,
        "lang": "en",
        "authorNames": ["Ada"],
        "tags": ["physics"],
        "categories": ["Essays"],
        "excerpt": "A short dek.",
        "html": "<p>Rendered body…</p>",
        "text": "Rendered body…",
        "media": [
            {
                "src": "https://old.blog/wp-content/uploads/2020/foo.jpg",
                "alt": "diagram",
                "title": None,
                "mimeType": None,
                "byteSize": None,
                "width": None,
                "height": None,
                "role": "inline",
            }
        ],
        "provenance": _provenance().model_dump(mode="json"),
    }
    data.update(overrides)
    return Article.model_validate(data)


def test_article_round_trip_example() -> None:
    article = _article()
    dumped = article.model_dump(mode="json", exclude_none=False)
    again = Article.model_validate(dumped)
    assert again.model_dump(mode="json") == dumped
    assert dumped["kind"] == "offprint-article"
    assert dumped["version"] == 1
    assert dumped["title"] == "Foo"
    assert dumped["provenance"]["extractorVersion"] == f"offprint/{__version__}"
    assert dumped["media"][0]["role"] == "inline"


def test_unknown_keys_are_dropped_and_not_reemitted() -> None:
    article = _article()
    raw = article.model_dump(mode="json")
    raw["unknownField"] = "nope"
    raw["provenance"] = {**raw["provenance"], "secret": "x"}
    raw["media"][0] = {**raw["media"][0], "extra": 1}
    parsed = Article.model_validate(raw)
    dumped = parsed.model_dump(mode="json", exclude_none=False)
    assert "unknownField" not in dumped
    assert "secret" not in dumped["provenance"]
    assert "extra" not in dumped["media"][0]


def test_title_is_string_not_null() -> None:
    article = _article(title="")
    assert article.title == ""
    with pytest.raises(ValidationError):
        _article(title=None)


def test_run_manifest_round_trip() -> None:
    manifest = RunManifest(
        origin="https://old.blog",
        startedAt="2026-08-25T12:00:00Z",
        finishedAt="2026-08-25T12:01:00Z",
        outPath="corpus.jsonl",
        result="partial",
        stats=RunStats(discovered=10, queued=8, extracted=2, skipped=0, failed=6),
        config=RunConfig(
            concurrency=4,
            delaySec=0.5,
            ignoreRobots=False,
            browser="fallback",
            maxBytes=10 * 1024 * 1024,
        ),
        failures=[RunFailure(url="https://old.blog/x", code="network", message="reset")],
        failuresTruncated=False,
        skippedSample=[],
    )
    dumped = manifest.model_dump(mode="json", exclude_none=False)
    assert dumped["kind"] == "offprint-run"
    assert dumped["result"] == "partial"
    assert dumped["stats"]["failed"] == 6
    assert RunManifest.model_validate(dumped).model_dump(mode="json") == dumped


def test_media_src_required() -> None:
    with pytest.raises(ValidationError):
        Media.model_validate({})


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("", None),
        ("   ", None),
        ("not-a-date", None),
        ("2020-13-01", None),
        ("2020-01-15", "2020-01-15T00:00:00Z"),
        ("2020-01-15T12:00:00Z", "2020-01-15T12:00:00Z"),
        ("2020-01-15T12:00:00+00:00", "2020-01-15T12:00:00Z"),
        ("Wed, 15 Jan 2020 12:00:00 GMT", "2020-01-15T12:00:00Z"),
        (date(2020, 1, 15), "2020-01-15T00:00:00Z"),
        (datetime(2020, 1, 15, 12, 0, 0, tzinfo=UTC), "2020-01-15T12:00:00Z"),
        (datetime(2020, 1, 15, 12, 0, 0), "2020-01-15T12:00:00Z"),
    ],
)
def test_parse_datetime(value: object, expected: str | None) -> None:
    assert parse_datetime(value) == expected


@pytest.mark.parametrize(
    ("exc_type", "code", "exit_code"),
    [
        (UsageError, "usage", 2),
        (BlockedUrlError, "ssrf_blocked", 3),
        (RobotsDeniedError, "robots_denied", 4),
        (NotArticleError, "not_an_article", 7),
        (SizeError, "too_large", 8),
        (SchemaError, "invalid_document", 8),
        (FetchError, "network", 6),
    ],
)
def test_error_codes(exc_type: type[OffprintError], code: str, exit_code: int) -> None:
    err = exc_type("boom", url="https://example.com/")
    assert isinstance(err, OffprintError)
    assert err.code == code
    assert err.exit_code == exit_code
    assert err.url == "https://example.com/"
    assert err.message == "boom"


def test_http_error_splits_4xx_5xx() -> None:
    not_found = HttpError("gone", status_code=404, url="https://x/")
    assert not_found.code == "http_4xx"
    assert not_found.exit_code == 5
    server = HttpError("oops", status_code=502, url="https://x/")
    assert server.code == "http_5xx"
    assert server.exit_code == 6


def test_article_schema_drift() -> None:
    path = REPO / "schemas" / "offprint-article.v1.json"
    committed = json.loads(path.read_text(encoding="utf-8"))
    generated = dump_article_schema()
    assert committed == generated
    assert path.read_text(encoding="utf-8") == schema_to_json(generated)


def test_run_schema_drift() -> None:
    path = REPO / "schemas" / "offprint-run.v1.json"
    committed = json.loads(path.read_text(encoding="utf-8"))
    generated = dump_run_schema()
    assert committed == generated
    assert path.read_text(encoding="utf-8") == schema_to_json(generated)


def test_published_schema_envelope() -> None:
    article = dump_article_schema()
    assert article["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert article["$id"].endswith("schemas/offprint-article.v1.json")
    assert article["title"] == "Offprint Article"
    assert article["additionalProperties"] is True
    run = dump_run_schema()
    assert run["title"] == "Offprint Run Manifest"
    assert run["additionalProperties"] is True
