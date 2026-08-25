"""Atomic state.json and site --resume."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from offprint.errors import UsageError
from offprint.site import SiteOptions, extract_site_async
from offprint.site.resume import ResumeState, load_state, write_state
from offprint.urls import canonical_key

HTML = Path(__file__).resolve().parents[2] / "fixtures" / "html"


def test_write_state_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    state = ResumeState(done={"https://example.com/a", "https://example.com/b"})
    write_state(path, state)
    loaded = load_state(path)
    assert loaded.done == state.done
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert data["done"] == sorted(state.done)
    assert not list(tmp_path.glob(".state.json.*.tmp"))


def test_load_state_missing(tmp_path: Path) -> None:
    assert load_state(tmp_path / "state.json").done == set()


def test_load_state_bad_version(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text('{"version": 2, "done": []}\n', encoding="utf-8")
    with pytest.raises(UsageError, match="unsupported state.json version"):
        load_state(path)


def test_load_state_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(UsageError, match="cannot read state.json"):
        load_state(path)


def test_write_state_replaces(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    write_state(path, ResumeState(done={"old"}))
    write_state(path, ResumeState(done={"new"}))
    assert load_state(path).done == {"new"}


@pytest.mark.asyncio
@respx.mock
async def test_extract_site_resume_skips_done(public_dns: None, tmp_path: Path) -> None:
    html = (HTML / "wordpress_entry_content.html").read_bytes()
    respx.get("https://example.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://example.com/blog/real-post").mock(
        return_value=httpx.Response(200, content=html, headers={"Content-Type": "text/html"})
    )
    urls = tmp_path / "urls.txt"
    urls.write_text("https://example.com/blog/real-post\n", encoding="utf-8")
    out = tmp_path / "corpus.jsonl"
    first = await extract_site_async(
        SiteOptions(
            origin="https://example.com",
            out_path=out,
            urls_file=urls,
            delay=0,
            concurrency=1,
            ignore_robots=True,
            no_crawl=True,
        )
    )
    assert first.stats.extracted == 1
    assert first.stats.resumed == 0
    key = canonical_key("https://example.com/blog/real-post")
    state = load_state(tmp_path / "state.json")
    assert key in state.done
    first_text = out.read_text(encoding="utf-8")
    assert first_text.count("\n") == 1

    second = await extract_site_async(
        SiteOptions(
            origin="https://example.com",
            out_path=out,
            urls_file=urls,
            delay=0,
            concurrency=1,
            ignore_robots=True,
            no_crawl=True,
            resume=True,
        )
    )
    assert second.result == "ok"
    assert second.stats.extracted == 0
    assert second.stats.resumed == 1
    assert out.read_text(encoding="utf-8") == first_text


@pytest.mark.asyncio
@respx.mock
async def test_extract_site_resume_appends_new_url(public_dns: None, tmp_path: Path) -> None:
    html = (HTML / "wordpress_entry_content.html").read_bytes()
    respx.get("https://example.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://example.com/blog/a").mock(
        return_value=httpx.Response(200, content=html, headers={"Content-Type": "text/html"})
    )
    respx.get("https://example.com/blog/b").mock(
        return_value=httpx.Response(200, content=html, headers={"Content-Type": "text/html"})
    )
    out = tmp_path / "corpus.jsonl"
    urls_a = tmp_path / "a.txt"
    urls_a.write_text("https://example.com/blog/a\n", encoding="utf-8")
    await extract_site_async(
        SiteOptions(
            origin="https://example.com",
            out_path=out,
            urls_file=urls_a,
            delay=0,
            concurrency=1,
            ignore_robots=True,
            no_crawl=True,
        )
    )
    urls_both = tmp_path / "both.txt"
    urls_both.write_text(
        "https://example.com/blog/a\nhttps://example.com/blog/b\n", encoding="utf-8"
    )
    manifest = await extract_site_async(
        SiteOptions(
            origin="https://example.com",
            out_path=out,
            urls_file=urls_both,
            delay=0,
            concurrency=1,
            ignore_robots=True,
            no_crawl=True,
            resume=True,
        )
    )
    assert manifest.stats.extracted == 1
    assert manifest.stats.resumed == 1
    lines = [ln for ln in out.read_text(encoding="utf-8").splitlines() if ln]
    assert len(lines) == 2


@pytest.mark.asyncio
@respx.mock
async def test_overwrite_resets_state(public_dns: None, tmp_path: Path) -> None:
    html = (HTML / "wordpress_entry_content.html").read_bytes()
    respx.get("https://example.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://example.com/blog/real-post").mock(
        return_value=httpx.Response(200, content=html, headers={"Content-Type": "text/html"})
    )
    urls = tmp_path / "urls.txt"
    urls.write_text("https://example.com/blog/real-post\n", encoding="utf-8")
    out = tmp_path / "corpus.jsonl"
    await extract_site_async(
        SiteOptions(
            origin="https://example.com",
            out_path=out,
            urls_file=urls,
            delay=0,
            concurrency=1,
            ignore_robots=True,
            no_crawl=True,
        )
    )
    out.write_text("stale\n", encoding="utf-8")
    manifest = await extract_site_async(
        SiteOptions(
            origin="https://example.com",
            out_path=out,
            urls_file=urls,
            delay=0,
            concurrency=1,
            ignore_robots=True,
            no_crawl=True,
            overwrite=True,
        )
    )
    assert manifest.stats.extracted == 1
    assert "stale" not in out.read_text(encoding="utf-8")
    assert (
        canonical_key("https://example.com/blog/real-post")
        in load_state(tmp_path / "state.json").done
    )


def test_resume_and_overwrite_conflict(tmp_path: Path) -> None:
    from offprint.site.job import extract_site

    out = tmp_path / "corpus.jsonl"
    out.write_text("x\n", encoding="utf-8")
    with pytest.raises(UsageError, match="either --resume or --overwrite"):
        extract_site(
            SiteOptions(
                origin="https://example.com",
                out_path=out,
                resume=True,
                overwrite=True,
            )
        )
