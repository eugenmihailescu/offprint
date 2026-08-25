"""httpx fetch with NullCookies, manual redirects, and a decompressed byte cap."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import EmailMessage
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version
from typing import Any
from urllib.parse import urljoin

import httpx
from charset_normalizer import from_bytes

from offprint.constants import (
    ACCEPT_HEADER,
    DEFAULT_CONNECT_TIMEOUT_SEC,
    DEFAULT_MAX_BYTES,
    DEFAULT_MAX_REDIRECTS,
    DEFAULT_POOL_TIMEOUT_SEC,
    DEFAULT_READ_TIMEOUT_SEC,
    MAX_BYTES_HARD_CAP,
    MAX_REDIRECTS_HARD_CAP,
    TIMEOUT_HARD_CAP_SEC,
    default_user_agent,
)
from offprint.errors import FetchError, HttpError, SizeError
from offprint.ssrf import assert_public_http_url

log = logging.getLogger("offprint.fetch")

HopCheck = Callable[[str], Awaitable[None]]


class NullCookies(httpx.Cookies):
    """Drop Set-Cookie / Cookie. ``cookies=None`` would install a real jar."""

    def extract_cookies(self, *args: Any, **kwargs: Any) -> None:
        return None

    def set(self, *args: Any, **kwargs: Any) -> None:  # type: ignore[override]
        return None

    def set_cookie_header(self, *args: Any, **kwargs: Any) -> None:  # type: ignore[override]
        return None

    def update(self, *args: Any, **kwargs: Any) -> None:  # type: ignore[override]
        return None


@dataclass(frozen=True)
class FetchResult:
    requested_url: str
    final_url: str
    status: int
    content_type: str | None
    body: bytes
    redirects: tuple[str, ...]
    fetched_at: datetime


async def _strip_cookie_header(request: httpx.Request) -> None:
    request.headers.pop("Cookie", None)
    request.headers.pop("cookie", None)


class FetchClient:
    """Wraps ``httpx.AsyncClient(cookies=NullCookies(), follow_redirects=False)``."""

    def __init__(
        self,
        *,
        timeout: float = DEFAULT_READ_TIMEOUT_SEC,
        connect_timeout: float = DEFAULT_CONNECT_TIMEOUT_SEC,
        max_bytes: int = DEFAULT_MAX_BYTES,
        max_redirects: int = DEFAULT_MAX_REDIRECTS,
        user_agent: str | None = None,
    ) -> None:
        try:
            version = pkg_version("offprint")
        except PackageNotFoundError:
            version = "0.0.0"
        self.user_agent = user_agent or default_user_agent(version)
        self._max_bytes = min(max(1, max_bytes), MAX_BYTES_HARD_CAP)
        self._max_redirects = min(max(0, max_redirects), MAX_REDIRECTS_HARD_CAP)
        read = min(timeout, TIMEOUT_HARD_CAP_SEC)
        connect = min(connect_timeout, TIMEOUT_HARD_CAP_SEC)
        pool = min(DEFAULT_POOL_TIMEOUT_SEC, TIMEOUT_HARD_CAP_SEC)
        self._client = httpx.AsyncClient(
            cookies=NullCookies(),
            follow_redirects=False,
            timeout=httpx.Timeout(connect=connect, read=read, write=read, pool=pool),
            headers={"User-Agent": self.user_agent, "Accept": ACCEPT_HEADER},
            event_hooks={"request": [_strip_cookie_header]},
            verify=True,
        )

    async def get(self, url: str, *, hop_ok: HopCheck | None = None) -> FetchResult:
        requested = url.strip()
        current = requested
        redirects: list[str] = []
        for _ in range(self._max_redirects + 1):
            await assert_public_http_url(current)
            if hop_ok is not None:
                await hop_ok(current)
            response = await self._send(current)
            try:
                if response.has_redirect_location:
                    location = response.headers.get("Location")
                    if not location:
                        raise FetchError("redirect without Location", url=current)
                    nxt = urljoin(str(response.url), location)
                    log.debug("redirect %s -> %s", current, nxt)
                    redirects.append(nxt)
                    current = nxt
                    continue
                if response.status_code >= 400:
                    raise HttpError(
                        f"HTTP {response.status_code}",
                        status_code=response.status_code,
                        url=current,
                    )
                body = await _read_capped(response, self._max_bytes, url=current)
            finally:
                await response.aclose()
            return FetchResult(
                requested_url=requested,
                final_url=current,
                status=response.status_code,
                content_type=response.headers.get("Content-Type"),
                body=body,
                redirects=tuple(redirects),
                fetched_at=datetime.now(UTC),
            )
        raise FetchError("too many redirects", url=requested)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _send(self, url: str) -> httpx.Response:
        request = self._client.build_request("GET", url)
        try:
            return await self._client.send(request, stream=True)
        except httpx.TimeoutException as exc:
            raise FetchError("timeout", url=url) from exc
        except httpx.HTTPError as exc:
            raise FetchError(str(exc) or "network error", url=url) from exc


async def _read_capped(response: httpx.Response, max_bytes: int, *, url: str) -> bytes:
    encoding = (response.headers.get("Content-Encoding") or "identity").lower()
    content_length = response.headers.get("Content-Length")
    if content_length and encoding in ("", "identity"):
        try:
            declared = int(content_length)
        except ValueError:
            declared = -1
        if declared > max_bytes:
            raise SizeError("response Content-Length exceeds cap", url=url)
    buf = bytearray()
    try:
        async for chunk in response.aiter_bytes():
            buf.extend(chunk)
            if len(buf) > max_bytes:
                raise SizeError("decompressed response exceeds cap", url=url)
    except SizeError:
        raise
    except httpx.HTTPError as exc:
        raise FetchError(str(exc) or "network error", url=url) from exc
    return bytes(buf)


def decode_body(body: bytes, content_type: str | None) -> str:
    """Decode via Content-Type charset, then charset-normalizer (not ``response.text``)."""
    charset = _charset_from_content_type(content_type)
    if charset:
        try:
            return body.decode(charset)
        except (LookupError, UnicodeDecodeError):
            pass
    match = from_bytes(body).best()
    if match is not None:
        return str(match)
    return body.decode("utf-8", errors="replace")


def _charset_from_content_type(content_type: str | None) -> str | None:
    if not content_type:
        return None
    msg = EmailMessage()
    msg["Content-Type"] = content_type
    return msg.get_content_charset()
