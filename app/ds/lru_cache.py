"""Least-recently-used cache: hash map + doubly linked list, O(1) get and put.

Thread-safe, with optional per-entry time-to-live, and hit/miss counters for /metrics.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Hashable
from dataclasses import dataclass
from typing import Generic, TypeVar

K = TypeVar("K", bound=Hashable)
V = TypeVar("V")


@dataclass
class _Entry(Generic[K, V]):
    key: K
    value: V
    expires_at: float
    prev: _Entry[K, V] | None = None
    next: _Entry[K, V] | None = None


class LRUCache(Generic[K, V]):
    def __init__(
        self, capacity: int, ttl_seconds: float | None = None, clock: Callable[[], float] = time.monotonic
    ) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self.capacity = capacity
        self.ttl = ttl_seconds
        self._clock = clock
        self._map: dict[K, _Entry[K, V]] = {}
        self._head: _Entry | None = None  # most recently used
        self._tail: _Entry | None = None  # least recently used
        self._lock = threading.Lock()
        self.hits = self.misses = self.evictions = 0

    def __len__(self) -> int:
        return len(self._map)

    def _unlink(self, e: _Entry) -> None:
        if e.prev:
            e.prev.next = e.next
        else:
            self._head = e.next
        if e.next:
            e.next.prev = e.prev
        else:
            self._tail = e.prev
        e.prev = e.next = None

    def _push_front(self, e: _Entry) -> None:
        e.next = self._head
        if self._head:
            self._head.prev = e
        self._head = e
        if self._tail is None:
            self._tail = e

    def get(self, key: K) -> V | None:
        with self._lock:
            e = self._map.get(key)
            if e is None or (self.ttl is not None and self._clock() >= e.expires_at):
                if e is not None:  # expired
                    self._unlink(e)
                    del self._map[key]
                self.misses += 1
                return None
            self._unlink(e)
            self._push_front(e)
            self.hits += 1
            return e.value

    def put(self, key: K, value: V) -> None:
        with self._lock:
            expires = self._clock() + self.ttl if self.ttl is not None else float("inf")
            e = self._map.get(key)
            if e is not None:
                e.value, e.expires_at = value, expires
                self._unlink(e)
                self._push_front(e)
                return
            if len(self._map) >= self.capacity and self._tail is not None:
                lru = self._tail
                self._unlink(lru)
                del self._map[lru.key]
                self.evictions += 1
            e = _Entry(key, value, expires)
            self._map[key] = e
            self._push_front(e)

    def keys_mru_first(self) -> list[K]:
        out, e = [], self._head
        while e:
            out.append(e.key)
            e = e.next
        return out

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0
