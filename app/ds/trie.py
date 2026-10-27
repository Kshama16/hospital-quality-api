"""Prefix tree for hospital-name autocomplete.

Insert: O(L) for a name of L characters. Search: O(P + k log k) for a prefix of P characters,
returning the k best matches. Each node keeps the IDs of every name that passes through it,
so a lookup never walks the subtree.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class _Node:
    children: dict[str, _Node] = field(default_factory=dict)
    ids: set[str] = field(default_factory=set)


class Trie:
    def __init__(self, max_ids_per_node: int | None = None) -> None:
        self._root = _Node()
        self._max = max_ids_per_node
        self.size = 0

    @staticmethod
    def tokens(text: str) -> list[str]:
        """Lower-cased words, so 'mass gen' matches 'Massachusetts General Hospital'."""
        return re.findall(r"[a-z0-9]+", text.lower())

    def insert(self, text: str, item_id: str) -> None:
        """Indexes every word of text, so a search can start at any word."""
        for word in self.tokens(text):
            node = self._root
            for ch in word:
                node = node.children.setdefault(ch, _Node())
                if self._max is None or len(node.ids) < self._max:
                    node.ids.add(item_id)
        self.size += 1

    def _prefix_ids(self, prefix: str) -> set[str]:
        node = self._root
        for ch in prefix:
            if ch not in node.children:
                return set()
            node = node.children[ch]
        return node.ids

    def search(self, query: str) -> set[str]:
        """IDs whose text contains a word starting with every query token (AND semantics)."""
        words = self.tokens(query)
        if not words:
            return set()
        result = set(self._prefix_ids(words[0]))
        for w in words[1:]:
            result &= self._prefix_ids(w)
            if not result:
                break
        return result
