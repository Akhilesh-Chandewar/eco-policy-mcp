"""Tiny async TTL cache with statistics.

Used to keep the AMFI NAV index (6h), NAV history (12h) and NSE quotes (60s)
in memory so repeated LLM tool-calls are fast and upstreams stay happy.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from .errors import EcoPolicyError


@dataclass
class _Entry:
    value: Any
    expires_at: float
    stored_at: float


class TTLCache:
    def __init__(self, default_ttl: float = 300.0) -> None:
        self.default_ttl = default_ttl
        self._store: dict[str, _Entry] = {}
        self._lock = asyncio.Lock()

    # -- basic ops -----------------------------------------------------------
    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        if time.monotonic() >= entry.expires_at:
            self._store.pop(key, None)
            return None
        return entry.value

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        now = time.monotonic()
        self._store[key] = _Entry(
            value=value, expires_at=now + (ttl or self.default_ttl), stored_at=now
        )

    def drop(self, key: str) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()

    # -- stats ---------------------------------------------------------------
    def stats(self) -> dict[str, Any]:
        now = time.monotonic()
        live = [k for k, e in self._store.items() if now < e.expires_at]
        return {"entries": len(self._store), "live": len(live), "keys": live}

    # -- concurrent-safe get-or-set -------------------------------------------
    async def get_or_set(
        self,
        key: str,
        factory: Callable[[], Awaitable[Any]],
        ttl: float | None = None,
    ) -> Any:
        """Return cached value, else run `factory` once and cache the result.

        Exceptions from `factory` are NOT cached (transient upstream failures
        should not poison the cache).
        """
        cached = self.get(key)
        if cached is not None:
            return cached
        async with self._lock:
            # double-check: another coroutine may have filled it while we waited
            cached = self.get(key)
            if cached is not None:
                return cached
            value = await factory()
            self.set(key, value, ttl)
            return value


# Module-level shared caches -------------------------------------------------
amfi_cache = TTLCache(default_ttl=6 * 3600)
nse_cache = TTLCache(default_ttl=60.0)


async def get_or_set(cache: TTLCache, key: str, factory: Callable[[], Awaitable[Any]], ttl: float | None = None) -> Any:
    try:
        return await cache.get_or_set(key, factory, ttl)
    except EcoPolicyError:
        raise  # do not cache-warden-wrap; errors must propagate as-is
