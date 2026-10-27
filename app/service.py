"""Business logic: caching, search, filtering, pagination and rankings over a repository."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TypeVar

from app.ds import LRUCache, Trie, top_k
from app.models import METRICS, Hospital
from app.repositories.base import HospitalRepository, RepositoryError
from app.resilience import CircuitBreaker, CircuitOpenError, retry

log = logging.getLogger(__name__)
T = TypeVar("T")


class ServiceUnavailable(Exception):
    """The data store is failing and no cached copy is available."""


class HospitalService:
    def __init__(
        self,
        repo: HospitalRepository,
        cache_size: int = 1024,
        cache_ttl: float | None = 300.0,
        breaker: CircuitBreaker | None = None,
        retry_attempts: int = 3,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self.repo = repo
        self.cache: LRUCache[str, object] = LRUCache(cache_size, cache_ttl)
        self.breaker = breaker or CircuitBreaker()
        self._attempts = retry_attempts
        self._sleep = sleep
        self.trie = Trie()
        self._names: dict[str, str] = {}
        for h in repo.scan():  # build the in-memory search index once
            self.trie.insert(f"{h.name} {h.city}", h.provider_id)
            self._names[h.provider_id] = h.name

    def _load(self, key: str, fn: Callable[[], T]) -> T:
        """Cache-aside read: cache hit, else repository call guarded by retry and the circuit breaker."""
        cached = self.cache.get(key)
        if cached is not None:
            return cached  # type: ignore[return-value]
        kwargs = {"attempts": self._attempts, "retry_on": (RepositoryError,)}
        if self._sleep:
            kwargs["sleep"] = self._sleep
        try:
            value = self.breaker.call(lambda: retry(fn, **kwargs))  # type: ignore[arg-type]
        except (RepositoryError, CircuitOpenError) as exc:
            log.warning("data store unavailable for %s: %s", key, exc)
            raise ServiceUnavailable(str(exc)) from exc
        if value is not None:
            self.cache.put(key, value)
        return value

    def get(self, provider_id: str) -> Hospital | None:
        return self._load(f"hospital:{provider_id}", lambda: self.repo.get(provider_id))

    def by_state(self, state: str) -> list[Hospital]:
        return self._load(f"state:{state}", lambda: self.repo.list_by_state(state))

    def list_state(
        self, state: str, min_rating: int | None = None, limit: int = 20, cursor: str | None = None
    ) -> tuple[list[Hospital], str | None]:
        """Keyset pagination: cursor is the last provider_id of the previous page."""
        rows = [
            h
            for h in self.by_state(state)
            if (min_rating is None or (h.overall_rating or 0) >= min_rating)
            and (cursor is None or h.provider_id > cursor)
        ]
        page = rows[:limit]
        return page, (page[-1].provider_id if len(rows) > limit else None)

    def search(self, query: str, limit: int = 10) -> list[Hospital]:
        ids = sorted(self.trie.search(query), key=lambda i: (self._names[i], i))[:limit]
        return [h for h in (self.get(i) for i in ids) if h is not None]

    def rank(self, metric: str, k: int = 10, state: str | None = None) -> list[Hospital]:
        if metric not in METRICS:
            raise ValueError(f"metric must be one of {sorted(METRICS)}")
        pool = self.by_state(state) if state else self._load("all", lambda: list(self.repo.scan()))
        return top_k(pool, k, key=lambda h: getattr(h, metric), largest=METRICS[metric])
