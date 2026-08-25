"""Typed failures with stable ``code`` strings and CLI exit codes."""

from __future__ import annotations


class OffprintError(Exception):
    """Base error. Wrappers should read ``code``; do not collapse shared exits."""

    code: str
    exit_code: int
    message: str
    url: str | None

    def __init__(
        self,
        message: str,
        *,
        code: str,
        exit_code: int,
        url: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.exit_code = exit_code
        self.url = url


class UsageError(OffprintError):
    def __init__(self, message: str, *, url: str | None = None) -> None:
        super().__init__(message, code="usage", exit_code=2, url=url)


class BlockedUrlError(OffprintError):
    def __init__(self, message: str, *, url: str | None = None) -> None:
        super().__init__(message, code="ssrf_blocked", exit_code=3, url=url)


class RobotsDeniedError(OffprintError):
    def __init__(self, message: str, *, url: str | None = None) -> None:
        super().__init__(message, code="robots_denied", exit_code=4, url=url)


class HttpError(OffprintError):
    status_code: int

    def __init__(self, message: str, *, status_code: int, url: str | None = None) -> None:
        if 400 <= status_code <= 499:
            code, exit_code = "http_4xx", 5
        else:
            code, exit_code = "http_5xx", 6
        super().__init__(message, code=code, exit_code=exit_code, url=url)
        self.status_code = status_code


class FetchError(OffprintError):
    def __init__(self, message: str, *, url: str | None = None) -> None:
        super().__init__(message, code="network", exit_code=6, url=url)


class NotArticleError(OffprintError):
    def __init__(self, message: str, *, url: str | None = None) -> None:
        super().__init__(message, code="not_an_article", exit_code=7, url=url)


class SizeError(OffprintError):
    def __init__(self, message: str, *, url: str | None = None) -> None:
        super().__init__(message, code="too_large", exit_code=8, url=url)


class SchemaError(OffprintError):
    def __init__(self, message: str, *, url: str | None = None) -> None:
        super().__init__(message, code="invalid_document", exit_code=8, url=url)
