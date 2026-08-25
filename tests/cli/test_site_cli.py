from pathlib import Path

import httpx
import pytest
import respx

from offprint.cli import main
from offprint.site import SiteOptions, extract_site_async

HTML = Path(__file__).resolve().parents[2] / "fixtures" / "html"


def test_site_requires_out() -> None:
    assert main(["--origin", "https://example.com"]) == 2


def test_site_existing_out_requires_overwrite(tmp_path: Path) -> None:
    dest = tmp_path / "corpus.jsonl"
    dest.write_text("x\n", encoding="utf-8")
    assert main(["--origin", "https://example.com", "--out", str(dest)]) == 2


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
