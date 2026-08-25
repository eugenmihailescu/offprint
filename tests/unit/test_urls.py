"""Origin, canonical keys, and www/apex matching."""

from __future__ import annotations

import pytest

from offprint.errors import UsageError
from offprint.urls import canonical_key, parse_origin, same_site_family, www_apex_twin


def test_parse_origin_strips_path_and_default_port() -> None:
    assert parse_origin("https://Old.Blog:443/foo?x=1#z") == "https://old.blog"
    assert parse_origin("http://old.blog:80") == "http://old.blog"
    assert parse_origin("https://old.blog:8443/x") == "https://old.blog:8443"


def test_parse_origin_rejects_bad() -> None:
    with pytest.raises(UsageError) as exc:
        parse_origin("not-a-url")
    assert exc.value.exit_code == 2
    with pytest.raises(UsageError):
        parse_origin("https://")


def test_canonical_key_strips_slash_fragment_tracking() -> None:
    a = canonical_key("HTTPS://Old.Blog/2020/foo/?utm_source=x&keep=1#frag")
    b = canonical_key("https://old.blog/2020/foo?keep=1")
    assert a == b
    assert a == "https://old.blog/2020/foo?keep=1"


def test_canonical_key_keeps_root_slash() -> None:
    assert canonical_key("https://old.blog/") == "https://old.blog/"
    assert canonical_key("https://old.blog") == "https://old.blog/"


def test_www_not_rewritten_in_key() -> None:
    apex = canonical_key("https://old.blog/post")
    www = canonical_key("https://www.old.blog/post")
    assert apex != www
    assert same_site_family(apex, www)
    assert same_site_family("https://old.blog", "http://www.old.blog")
    assert not same_site_family("https://old.blog", "https://cdn.old.blog")


def test_www_apex_twin() -> None:
    assert www_apex_twin("https://old.blog") == "https://www.old.blog"
    assert www_apex_twin("https://www.old.blog") == "https://old.blog"
