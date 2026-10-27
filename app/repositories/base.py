"""Storage interface. The service layer depends on this, not on a specific database."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator

from app.models import Hospital


class RepositoryError(Exception):
    """A storage call failed (timeout, throttling, connection error). Safe to retry."""


class HospitalRepository(ABC):
    @abstractmethod
    def get(self, provider_id: str) -> Hospital | None: ...

    @abstractmethod
    def list_by_state(self, state: str) -> list[Hospital]:
        """All hospitals in a state, ordered by provider_id."""

    @abstractmethod
    def scan(self) -> Iterator[Hospital]:
        """Every hospital; used once at startup to build the search index."""

    @abstractmethod
    def put_many(self, hospitals: Iterable[Hospital]) -> int: ...

    @abstractmethod
    def count(self) -> int: ...
