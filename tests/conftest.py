"""Shared fixtures. Default tests stay offline."""

from __future__ import annotations

import pytest

from offprint import ssrf


@pytest.fixture
def public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolve every hostname to a public address (no real DNS)."""

    def fake_lookup(hostname: str) -> list[str]:
        return ["8.8.8.8"]

    monkeypatch.setattr(ssrf, "lookup_host", fake_lookup)
