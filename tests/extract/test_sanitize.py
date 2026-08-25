"""Sanitize allowlist and URL policy."""

from __future__ import annotations

from offprint.extract.sanitize import sanitize


def test_drops_script_and_javascript_href() -> None:
    html = (
        "<p>ok</p><script>alert(1)</script>"
        '<a href="javascript:alert(1)">x</a>'
        '<a href="https://example.com/p">y</a>'
    )
    out = sanitize(html, base_url="https://example.com/")
    assert "script" not in out.lower()
    assert "javascript:" not in out.lower()
    assert "https://example.com/p" in out


def test_keeps_youtube_and_vimeo_drops_other_iframe() -> None:
    html = (
        '<iframe src="https://www.youtube.com/embed/abc"></iframe>'
        '<iframe src="https://player.vimeo.com/video/1"></iframe>'
        '<iframe src="https://evil.example/embed"></iframe>'
    )
    out = sanitize(html, base_url="https://example.com/")
    assert "youtube.com/embed/abc" in out
    assert "player.vimeo.com/video/1" in out
    assert "evil.example" in out
    assert out.lower().count("<iframe") == 2


def test_keeps_data_latex_and_tex_class() -> None:
    html = (
        '<p>n</p><img class="tex" src="/eq.png" alt="E=mc^2" data-latex="E=mc^2">'
        '<span data-latex="x^2">x^2</span>'
    )
    out = sanitize(html, base_url="https://example.com/")
    assert "data-latex" in out
    assert 'class="tex"' in out or "class='tex'" in out
    assert "eq.png" in out
