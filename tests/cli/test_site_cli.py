from pathlib import Path

import httpx
import pytest
import respx

from offprint.cli import main
from offprint.model import RunConfig, RunManifest, RunStats
from offprint.site import SiteOptions, extract_site_async

HTML = Path(__file__).resolve().parents[2] / "fixtures" / "html"


def test_site_requires_out() -> None:
    assert main(["--origin", "https://example.com"]) == 2


def test_site_existing_out_requires_overwrite(tmp_path: Path) -> None:
    dest = tmp_path / "corpus.jsonl"
    dest.write_text("x\n", encoding="utf-8")
    assert main(["--origin", "https://example.com", "--out", str(dest)]) == 2


def test_cli_progress_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def fake(options):
        seen["options"] = options
        return _ok_manifest()

    monkeypatch.setattr("offprint.cli.extract_site", fake)
    code = main(
        [
            "site",
            "--origin",
            "https://example.com",
            "--out",
            "c.jsonl",
            "--progress",
        ]
    )
    assert code == 0
    opts = seen["options"]
    assert isinstance(opts, SiteOptions)
    assert opts.progress is True


def test_cli_quiet_disables_progress(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def fake(options):
        seen["options"] = options
        return _ok_manifest()

    monkeypatch.setattr("offprint.cli.extract_site", fake)
    main(
        [
            "site",
            "--origin",
            "https://example.com",
            "--out",
            "c.jsonl",
            "--progress",
            "-q",
        ]
    )
    opts = seen["options"]
    assert isinstance(opts, SiteOptions)
    assert opts.progress is False


def test_cli_resume_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def fake(options):
        seen["options"] = options
        return _ok_manifest()

    monkeypatch.setattr("offprint.cli.extract_site", fake)
    code = main(
        [
            "site",
            "--origin",
            "https://example.com",
            "--out",
            "c.jsonl",
            "--resume",
        ]
    )
    assert code == 0
    opts = seen["options"]
    assert isinstance(opts, SiteOptions)
    assert opts.resume is True


def test_cli_resume_and_overwrite_conflict(tmp_path: Path) -> None:
    dest = tmp_path / "corpus.jsonl"
    dest.write_text("x\n", encoding="utf-8")
    assert (
        main(
            [
                "site",
                "--origin",
                "https://example.com",
                "--out",
                str(dest),
                "--resume",
                "--overwrite",
            ]
        )
        == 2
    )


@pytest.mark.asyncio
@respx.mock
async def test_extract_site_urls_file(public_dns: None, tmp_path: Path) -> None:
    html = (HTML / "wordpress_entry_content.html").read_bytes()
    respx.get("https://example.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://example.com/blog/real-post").mock(
        return_value=httpx.Response(200, content=html, headers={"Content-Type": "text/html"})
    )
    urls = tmp_path / "urls.txt"
    urls.write_text("# comment\nhttps://example.com/blog/real-post\n", encoding="utf-8")
    out = tmp_path / "corpus.jsonl"
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
    assert out.is_file()
    assert manifest.result == "ok"
    assert manifest.stats.extracted == 1
    assert (tmp_path / "manifest.json").is_file() or out.parent.joinpath("manifest.json").is_file()


@pytest.mark.asyncio
@respx.mock
async def test_extract_site_progress_stderr(
    public_dns: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
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
            overwrite=True,
            progress=True,
        )
    )
    err = capsys.readouterr().err
    assert "discover urls-file" in err
    assert "extract 1/1" in err
    assert "eta=" in err
    assert "extracted=1" in err


@respx.mock
def test_cli_site_overwrite(public_dns: None, tmp_path: Path) -> None:
    html = (HTML / "wordpress_entry_content.html").read_bytes()
    respx.get("https://example.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://example.com/blog/real-post").mock(
        return_value=httpx.Response(200, content=html, headers={"Content-Type": "text/html"})
    )
    respx.route().mock(return_value=httpx.Response(404))
    urls = tmp_path / "urls.txt"
    urls.write_text("https://example.com/blog/real-post\n", encoding="utf-8")
    dest = tmp_path / "corpus.jsonl"
    dest.write_text("old\n", encoding="utf-8")
    code = main(
        [
            "site",
            "--origin",
            "https://example.com",
            "--urls-file",
            str(urls),
            "--out",
            str(dest),
            "--overwrite",
            "--delay",
            "0",
            "--concurrency",
            "1",
            "--ignore-robots",
            "--no-crawl",
        ]
    )
    assert code == 0
    assert "old" not in dest.read_text(encoding="utf-8")
    assert dest.read_text(encoding="utf-8").strip()


def _ok_manifest() -> RunManifest:
    return RunManifest(
        origin="https://example.com",
        startedAt="2026-08-25T12:00:00Z",
        finishedAt="2026-08-25T12:01:00Z",
        outPath="corpus.jsonl",
        result="ok",
        stats=RunStats(extracted=1, queued=1),
        config=RunConfig(
            concurrency=2,
            delaySec=0.5,
            ignoreRobots=False,
            browser="on",
            maxBytes=10 * 1024 * 1024,
        ),
    )


def test_cli_browser_missing_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("offprint.extract.browser.playwright_available", lambda: False)

    def boom(options):
        raise AssertionError("must not run site")

    monkeypatch.setattr("offprint.cli.extract_site", boom)
    assert (
        main(
            [
                "site",
                "--origin",
                "https://example.com",
                "--out",
                "c.jsonl",
                "--browser",
            ]
        )
        == 2
    )


def test_cli_browser_default_concurrency(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("offprint.extract.browser.playwright_available", lambda: True)
    seen: dict[str, object] = {}

    def fake(options):
        seen["options"] = options
        return _ok_manifest()

    monkeypatch.setattr("offprint.cli.extract_site", fake)
    code = main(
        [
            "site",
            "--origin",
            "https://example.com",
            "--out",
            "c.jsonl",
            "--browser",
        ]
    )
    assert code == 0
    opts = seen["options"]
    assert isinstance(opts, SiteOptions)
    assert opts.browser is True
    assert opts.concurrency is None
    assert opts.capped_concurrency() == 2
