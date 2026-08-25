"""stdlib logging for the CLI. JSON lines on stderr when requested."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
        }
        url = getattr(record, "url", None)
        code = getattr(record, "code", None)
        if url:
            payload["url"] = url
        if code:
            payload["code"] = code
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(*, verbose: int = 0, quiet: bool = False, fmt: str = "text") -> None:
    if quiet:
        level = logging.WARNING
    elif verbose >= 2:
        level = logging.DEBUG
    elif verbose >= 1:
        level = logging.INFO
    else:
        level = logging.WARNING
    handler = logging.StreamHandler(sys.stderr)
    if fmt == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    log = logging.getLogger("offprint")
    log.handlers.clear()
    log.addHandler(handler)
    log.setLevel(level)
    log.propagate = False
