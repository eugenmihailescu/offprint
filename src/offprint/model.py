"""Pydantic v1 interchange models. CamelCase field names match JSON 1:1."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Method = Literal["rss", "jsonld", "html-article", "trafilatura", "browser"]
MediaRole = Literal["inline", "feature", "og", "embed"]
TruncatedField = Literal["title", "excerpt", "text", "authorNames", "tags", "categories", "media"]
RunResult = Literal["ok", "partial", "empty_queue", "skipped_all", "interrupted"]
BrowserMode = Literal["off", "fallback", "on"]
SHA256_HEX = r"^[0-9a-f]{64}$"


class CamelModel(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        extra="ignore",
        ser_json_bytes="utf8",
    )


class Media(CamelModel):
    src: str = Field(max_length=4096)
    alt: str | None = Field(default=None, max_length=1000)
    title: str | None = Field(default=None, max_length=500)
    mimeType: str | None = Field(default=None, max_length=127)
    byteSize: int | None = Field(default=None, ge=0)
    width: int | None = Field(default=None, ge=0)
    height: int | None = Field(default=None, ge=0)
    role: MediaRole = "inline"


class Provenance(CamelModel):
    method: Method
    methodChain: list[str] = Field(default_factory=list, max_length=16)
    fetchedAt: str
    finalUrl: str = Field(max_length=2048)
    httpStatus: int = 200
    contentType: str | None = None
    bytes: int | None = Field(default=None, ge=0)
    redirects: list[str] = Field(default_factory=list, max_length=10)
    extractorVersion: str
    rawHtmlSha256: str | None = Field(default=None, pattern=SHA256_HEX)
    rawHtmlPath: str | None = None
    robotsIgnored: bool = False
    truncated: list[TruncatedField] = Field(default_factory=list, max_length=8)


class Article(CamelModel):
    kind: Literal["offprint-article"] = "offprint-article"
    version: Literal[1] = 1
    origin: str = Field(
        min_length=8,
        max_length=2048,
        description=(
            "Operator origin (scheme://host[:port]). "
            "Part of the consumer idempotency key with canonicalUrl."
        ),
    )
    canonicalUrl: str = Field(min_length=8, max_length=2048)
    discoveredUrls: list[Annotated[str, Field(max_length=2048)]] = Field(
        default_factory=list,
        max_length=50,
    )
    title: str = Field(default="", max_length=500)
    publishedAt: str | None = None
    updatedAt: str | None = None
    lang: str | None = Field(default=None, max_length=16)
    authorNames: list[Annotated[str, Field(max_length=200)]] = Field(
        default_factory=list,
        max_length=12,
    )
    tags: list[Annotated[str, Field(max_length=120)]] = Field(default_factory=list, max_length=64)
    categories: list[Annotated[str, Field(max_length=120)]] = Field(
        default_factory=list,
        max_length=32,
    )
    excerpt: str | None = Field(default=None, max_length=4000)
    html: str = Field(default="", max_length=5_000_000)
    text: str = Field(default="", max_length=1_000_000)
    media: list[Media] = Field(default_factory=list, max_length=500)
    provenance: Provenance


class RunFailure(CamelModel):
    url: str
    code: str
    message: str = ""


class RunStats(CamelModel):
    discovered: int = Field(default=0, ge=0)
    queued: int = Field(default=0, ge=0)
    extracted: int = Field(default=0, ge=0)
    skipped: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)
    resumed: int = Field(default=0, ge=0)
    notAttempted: int = Field(default=0, ge=0)


class RunConfig(CamelModel):
    concurrency: int
    delaySec: float
    ignoreRobots: bool
    browser: BrowserMode
    maxBytes: int


class RunManifest(CamelModel):
    kind: Literal["offprint-run"] = "offprint-run"
    version: Literal[1] = 1
    origin: str = Field(max_length=2048)
    startedAt: str
    finishedAt: str | None = None
    outPath: str
    result: RunResult
    stats: RunStats
    config: RunConfig
    failures: list[RunFailure] = Field(default_factory=list, max_length=200)
    failuresTruncated: bool = False
    skippedSample: list[RunFailure] = Field(default_factory=list, max_length=50)
