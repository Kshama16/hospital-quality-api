"""Retry with exponential backoff and a circuit breaker for calls to the data store."""

from __future__ import annotations

import random
import threading
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


def retry(
    fn: Callable[[], T],
    *,
    attempts: int = 3,
    base_delay: float = 0.05,
    max_delay: float = 1.0,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
    sleep: Callable[[float], None] = time.sleep,
    rng: random.Random | None = None,
) -> T:
    """Calls fn, retrying failures with exponential backoff and full jitter:
    wait uniform(0, min(max_delay, base_delay * 2**attempt))."""
    rng = rng or random.Random()
    for attempt in range(attempts):
        try:
            return fn()
        except retry_on:
            if attempt == attempts - 1:
                raise
            sleep(rng.uniform(0, min(max_delay, base_delay * 2**attempt)))
    raise AssertionError("unreachable")


class CircuitOpenError(Exception):
    """The breaker is open: the dependency failed repeatedly, so calls fail fast."""


class CircuitBreaker:
    """CLOSED -> (failure_threshold consecutive failures) -> OPEN -> (reset_timeout) -> HALF_OPEN.
    In HALF_OPEN one trial call is allowed: success closes the breaker, failure reopens it."""

    CLOSED, OPEN, HALF_OPEN = "closed", "open", "half_open"

    def __init__(
        self, failure_threshold: int = 5, reset_timeout: float = 30.0, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self._clock = clock
        self._state = self.CLOSED
        self._failures = 0
        self._opened_at = 0.0
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        with self._lock:
            if self._state == self.OPEN and self._clock() - self._opened_at >= self.reset_timeout:
                self._state = self.HALF_OPEN
            return self._state

    def call(self, fn: Callable[[], T]) -> T:
        if self.state == self.OPEN:
            raise CircuitOpenError("circuit open")
        try:
            result = fn()
        except Exception:
            with self._lock:
                self._failures += 1
                if self._state == self.HALF_OPEN or self._failures >= self.failure_threshold:
                    self._state, self._opened_at = self.OPEN, self._clock()
            raise
        with self._lock:
            self._failures, self._state = 0, self.CLOSED
        return result
