"""A tiny in-process TTL cache.

Elexon is fast but not free, and a month of either dataset is a couple of
megabytes. Repeated dashboard loads with the same parameters should not refetch
it. Deliberately not a distributed cache: a single process is all this service
needs, and on a serverless host each instance keeps its own copy, which is
correct but cold more often.

Entries are immutable analysis outputs keyed by request parameters, so a stale
read can only ever be *old*, never wrong for its key.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import Generic, TypeVar

T = TypeVar("T")


class TTLCache(Generic[T]):
    """Least-recently-used cache with per-entry expiry."""

    def __init__(self, *, ttl_seconds: int, max_entries: int) -> None:
        self._ttl = max(0, ttl_seconds)
        self._max = max(1, max_entries)
        self._entries: OrderedDict[str, tuple[float, T]] = OrderedDict()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> T | None:
        entry = self._entries.get(key)
        if entry is None:
            self.misses += 1
            return None
        stored_at, value = entry
        if self._ttl and (time.monotonic() - stored_at) > self._ttl:
            del self._entries[key]
            self.misses += 1
            return None
        self._entries.move_to_end(key)
        self.hits += 1
        return value

    def set(self, key: str, value: T) -> None:
        self._entries[key] = (time.monotonic(), value)
        self._entries.move_to_end(key)
        while len(self._entries) > self._max:
            self._entries.popitem(last=False)

    def stats(self) -> dict:
        return {
            "entries": len(self._entries),
            "max_entries": self._max,
            "ttl_seconds": self._ttl,
            "hits": self.hits,
            "misses": self.misses,
        }

    def clear(self) -> None:
        self._entries.clear()
