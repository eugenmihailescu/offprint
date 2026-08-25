"""Optional live extracts. Default pytest is ``-m 'not live'``.

Listed origins (do **not** add mynixworld.info — wrong repo coupling):

- https://blog.python.org/
- https://www.w3.org/blog/

Hit the network only when ``OFFPRINT_LIVE=1`` (still requires ``pytest -m live``).
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.live

LIVE_URLS = (
    "https://blog.python.org/",
    "https://www.w3.org/blog/",
)


@pytest.mark.parametrize("url", LIVE_URLS)
def test_public_example(url: str) -> None:
    if os.environ.get("OFFPRINT_LIVE") != "1":
        pytest.skip("set OFFPRINT_LIVE=1 to fetch public blogs")
    from offprint.pipeline import extract_url

    article = extract_url(url)
    assert article.text
    assert article.provenance.method
