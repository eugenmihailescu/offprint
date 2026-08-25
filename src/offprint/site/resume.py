"""Atomic ``state.json`` for ``--resume`` (canonical_key set)."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from offprint.errors import UsageError
from offprint.model import Article
from offprint.urls import canonical_key

STATE_VERSION = 1


@dataclass
class ResumeState:
    done: set[str] = field(default_factory=set)


def state_path(out_dir: Path) -> Path:
    return out_dir / "state.json"


def load_state(path: Path) -> ResumeState:
    if not path.exists():
        return ResumeState()
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise UsageError(f"cannot read state.json: {exc}", url=str(path)) from exc
    if not isinstance(data, dict):
        raise UsageError("state.json must be an object", url=str(path))
    version = data.get("version")
    if version != STATE_VERSION:
        raise UsageError(f"unsupported state.json version: {version!r}", url=str(path))
    done = data.get("done")
    if not isinstance(done, list):
        raise UsageError("state.json done must be a list", url=str(path))
    keys: set[str] = set()
    for item in done:
        if isinstance(item, str) and item:
            keys.add(item)
    return ResumeState(done=keys)


def write_state(path: Path, state: ResumeState) -> None:
    """Temp file + ``os.replace`` so a crash never truncates ``state.json`` in place."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        {"version": STATE_VERSION, "done": sorted(state.done)},
        ensure_ascii=False,
    )
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def article_keys(article: Article, requested: str) -> set[str]:
    """Canonical keys to mark done so aliases resume-skip on the next run."""
    keys: set[str] = set()
    for raw in (
        requested,
        article.canonicalUrl,
        article.provenance.finalUrl,
        *article.discoveredUrls,
    ):
        if not raw:
            continue
        try:
            keys.add(canonical_key(raw))
        except Exception:
            continue
    return keys
