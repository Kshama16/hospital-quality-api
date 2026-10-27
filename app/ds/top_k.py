"""Top-k selection with a bounded min-heap: O(n log k) time, O(k) memory.

Faster than sorting all n items (O(n log n)) when k is small, e.g. the 10 best hospitals in a
state. Implemented without heapq to show the sift operations.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TypeVar

T = TypeVar("T")


class MinHeap:
    """Binary min-heap of (key, tiebreak, item) tuples stored in a list."""

    def __init__(self) -> None:
        self.a: list[tuple] = []

    def __len__(self) -> int:
        return len(self.a)

    def peek(self) -> tuple:
        return self.a[0]

    def push(self, x: tuple) -> None:
        a = self.a
        a.append(x)
        i = len(a) - 1
        while i > 0:  # sift up
            parent = (i - 1) // 2
            if a[i][:2] >= a[parent][:2]:
                break
            a[i], a[parent] = a[parent], a[i]
            i = parent

    def replace_top(self, x: tuple) -> None:
        a = self.a
        a[0] = x
        i, n = 0, len(a)
        while True:  # sift down
            left, right, smallest = 2 * i + 1, 2 * i + 2, i
            if left < n and a[left][:2] < a[smallest][:2]:
                smallest = left
            if right < n and a[right][:2] < a[smallest][:2]:
                smallest = right
            if smallest == i:
                return
            a[i], a[smallest] = a[smallest], a[i]
            i = smallest


def top_k(items: Iterable[T], k: int, key: Callable[[T], float | None], largest: bool = True) -> list[T]:
    """The k items with the largest (or smallest) key, best first. Items with key None are skipped.
    Ties keep the earlier item."""
    if k <= 0:
        return []
    heap = MinHeap()
    for i, item in enumerate(items):
        v = key(item)
        if v is None:
            continue
        score = v if largest else -v
        entry = (score, -i, item)  # -i: on equal scores the earlier item ranks higher
        if len(heap) < k:
            heap.push(entry)
        elif entry[:2] > heap.peek()[:2]:
            heap.replace_top(entry)
    return [e[2] for e in sorted(heap.a, key=lambda e: e[:2], reverse=True)]
