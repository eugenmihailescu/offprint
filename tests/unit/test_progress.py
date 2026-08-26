"""Site --progress formatting and stderr lines."""

from __future__ import annotations

from io import StringIO

from offprint.progress import Progress, extract_eta, format_duration


def test_format_duration() -> None:
    assert format_duration(0) == "0s"
    assert format_duration(9.4) == "9s"
    assert format_duration(61) == "1m01s"
    assert format_duration(3600) == "1h00m"
    assert format_duration(3723) == "1h02m"
    assert format_duration(-1) == "?"
    assert format_duration(float("inf")) == "?"


def test_extract_eta() -> None:
    assert extract_eta(elapsed=10, paid=0, remaining=5) == "?"
    assert extract_eta(elapsed=0, paid=2, remaining=5) == "?"
    assert extract_eta(elapsed=10, paid=2, remaining=0) == "0s"
    # 2 paid in 10s → 5s/url × 8 remaining = 40s
    assert extract_eta(elapsed=10, paid=2, remaining=8) == "40s"


def test_progress_disabled_is_silent() -> None:
    buf = StringIO()
    prog = Progress(enabled=False, stream=buf, tty=False)
    prog.discover("sitemaps", sitemaps=1, locs=4)
    prog.extract_begin(4)
    prog.close()
    assert buf.getvalue() == ""


def test_progress_extract_eta_line() -> None:
    clock = {"t": 0.0}

    def now() -> float:
        return clock["t"]

    buf = StringIO()
    prog = Progress(enabled=True, stream=buf, tty=False, monotonic=now, min_interval=0.0)
    prog.extract_begin(10)
    clock["t"] = 10.0
    prog.extract_tick(
        extracted=2,
        failed=0,
        skipped=0,
        resumed=0,
        not_attempted=0,
        queued=10,
        force=True,
    )
    text = buf.getvalue()
    assert "extract 0/10" in text
    assert "extract 2/10" in text
    assert "extracted=2" in text
    assert "elapsed=10s" in text
    assert "eta=40s" in text


def test_progress_resume_excluded_from_rate() -> None:
    clock = {"t": 0.0}

    def now() -> float:
        return clock["t"]

    buf = StringIO()
    prog = Progress(enabled=True, stream=buf, tty=False, monotonic=now, min_interval=0.0)
    prog.extract_begin(10)
    clock["t"] = 10.0
    prog.extract_tick(
        extracted=1,
        failed=0,
        skipped=0,
        resumed=4,
        not_attempted=0,
        queued=10,
        force=True,
    )
    # paid=1 in 10s, remaining=5 → eta=50s (resume does not speed the rate)
    assert "extract 5/10" in buf.getvalue()
    assert "resumed=4" in buf.getvalue()
    assert "eta=50s" in buf.getvalue()


def test_progress_tty_rewrites_one_line() -> None:
    buf = StringIO()
    prog = Progress(enabled=True, stream=buf, tty=True, min_interval=0.0)
    prog.discover("sitemaps", sitemaps=1, locs=3)
    prog.discover("sitemaps", sitemaps=2, locs=9)
    prog.close()
    out = buf.getvalue()
    assert out.startswith("\r")
    assert out.endswith("\n")
    assert out.count("\n") == 1


def test_progress_break_line_before_log() -> None:
    buf = StringIO()
    prog = Progress(enabled=True, stream=buf, tty=True, min_interval=0.0)
    prog.discover("sitemaps", sitemaps=1, locs=1)
    prog.break_line()
    buf.write("ERROR boom\n")
    out = buf.getvalue()
    assert "\nERROR boom\n" in out
