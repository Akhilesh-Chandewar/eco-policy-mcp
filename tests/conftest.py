"""Shared fixtures: fake HTTP layer for the AMFI provider."""

from __future__ import annotations

from pathlib import Path

import pytest

import eco_policy_mcp.providers.amfi as amfi


class FakeResponse:
    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeClient:
    def __init__(self, text: str) -> None:
        self.text = text

    async def get(self, url, **kwargs):  # noqa: ANN001, ANN003
        return FakeResponse(self.text)


@pytest.fixture()
def amfi_sample(monkeypatch: pytest.MonkeyPatch) -> str:
    """Patch the AMFI HTTP boundary with the NAVAll sample fixture."""
    sample = (Path(__file__).parent / "fixtures" / "NAVAll_sample.txt").read_text()
    amfi_cache = __import__("eco_policy_mcp.cache", fromlist=["amfi_cache"]).amfi_cache
    amfi_cache.clear()
    monkeypatch.setattr(amfi, "get_client", lambda: FakeClient(sample))
    return sample


@pytest.fixture()
def history_patch(monkeypatch: pytest.MonkeyPatch):
    """Replace _fetch_history with canned rows; returns a setter."""

    def _set(rows: list[dict], scheme_name: str = "Test Fund") -> None:
        async def fake_fetch(code: str) -> dict:
            return {"meta": {"scheme_name": scheme_name}, "history": rows}

        monkeypatch.setattr(amfi, "_fetch_history", fake_fetch)

    return _set
