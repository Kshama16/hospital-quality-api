"""Token-bucket rate limiter: each client gets `capacity` tokens, refilled at `rate` per second.

Allows short bursts while capping the sustained request rate. O(1) per request.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable


class TokenBucket:
    def __init__(
        self, rate: float, capacity: int, clock: Callable[[], float] = time.monotonic, max_clients: int = 10_000
    ) -> None:
        self.rate = rate
        self.capacity = capacity
        self._clock = clock
        self._max_clients = max_clients
        self._buckets: dict[str, tuple[float, float]] = {}  # client -> (tokens, last refill time)
        self._lock = threading.Lock()

    def allow(self, client: str) -> bool:
        with self._lock:
            now = self._clock()
            tokens, last = self._buckets.get(client, (float(self.capacity), now))
            tokens = min(self.capacity, tokens + (now - last) * self.rate)
            allowed = tokens >= 1
            if allowed:
                tokens -= 1
            if client not in self._buckets and len(self._buckets) >= self._max_clients:
                self._buckets.pop(next(iter(self._buckets)))  # drop the oldest client entry
            self._buckets[client] = (tokens, now)
            return allowed

    def retry_after(self, client: str) -> float:
        """Seconds until the client has a full token again."""
        tokens, _ = self._buckets.get(client, (float(self.capacity), 0.0))
        return max(0.0, (1 - tokens) / self.rate)
