"""Parse datetimes to UTC ISO-8601 with a ``Z`` suffix. No python-dateutil."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime
from typing import Any

_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_datetime(value: Any) -> str | None:
    """Return ``YYYY-MM-DDTHH:MM:SSZ`` or ``None`` if the value is missing/invalid.

    Date-only strings become midnight UTC. Naive datetimes are treated as UTC.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        dt = datetime(value.year, value.month, value.day, tzinfo=UTC)
    elif isinstance(value, str):
        dt = _parse_str(value.strip())
        if dt is None:
            return None
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    else:
        dt = dt.astimezone(UTC)
    return dt.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_str(raw: str) -> datetime | None:
    if not raw:
        return None
    iso = f"{raw}T00:00:00+00:00" if _DATE_ONLY.fullmatch(raw) else raw
    if iso.endswith("Z"):
        iso = f"{iso[:-1]}+00:00"
    try:
        return datetime.fromisoformat(iso)
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(raw)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None
