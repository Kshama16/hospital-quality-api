import random

import pytest

from app.ds import LRUCache, TokenBucket, Trie, top_k


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


# ---- Trie -------------------------------------------------------------------------------
def test_trie_prefix_on_any_word_and_multiword_and():
    t = Trie()
    t.insert("Massachusetts General Hospital Boston", "1")
    t.insert("Mass Eye And Ear Boston", "2")
    t.insert("General Hospital Of Maine", "3")
    assert t.search("mass") == {"1", "2"}
    assert t.search("mass gen") == {"1"}
    assert t.search("GENERAL") == {"1", "3"}
    assert t.search("bos ear") == {"2"}
    assert t.search("zzz") == set() and t.search("  ") == set()


def test_trie_matches_brute_force_on_real_names(all_hospitals):
    t = Trie()
    for h in all_hospitals:
        t.insert(h.name, h.provider_id)
    for q in ["saint", "st mary", "children", "univ med", "kaiser"]:
        words = Trie.tokens(q)
        expected = {
            h.provider_id
            for h in all_hospitals
            if all(any(tok.startswith(w) for tok in Trie.tokens(h.name)) for w in words)
        }
        assert t.search(q) == expected


# ---- LRU cache ----------------------------------------------------------------------------
def test_lru_evicts_least_recently_used():
    c: LRUCache[str, int] = LRUCache(2)
    c.put("a", 1)
    c.put("b", 2)
    assert c.get("a") == 1  # a becomes most recent
    c.put("c", 3)  # evicts b
    assert c.get("b") is None and c.get("a") == 1 and c.get("c") == 3
    assert c.keys_mru_first() == ["c", "a"] and c.evictions == 1


def test_lru_update_existing_and_ttl():
    clock = FakeClock()
    c: LRUCache[str, int] = LRUCache(2, ttl_seconds=10, clock=clock)
    c.put("a", 1)
    c.put("a", 2)
    assert len(c) == 1 and c.get("a") == 2
    clock.t = 10
    assert c.get("a") is None and len(c) == 0


def test_lru_matches_reference_model_under_random_operations():
    rng = random.Random(7)
    c: LRUCache[int, int] = LRUCache(5)
    ref: list[tuple[int, int]] = []  # most recent last
    for _ in range(5000):
        k = rng.randrange(12)
        if rng.random() < 0.5:
            ref = [(kk, vv) for kk, vv in ref if kk != k] + [(k, k * 10)]
            ref = ref[-5:]
            c.put(k, k * 10)
        else:
            hit = next((v for kk, v in ref if kk == k), None)
            if hit is not None:
                ref = [(kk, vv) for kk, vv in ref if kk != k] + [(k, hit)]
            assert c.get(k) == hit
    assert c.keys_mru_first() == [k for k, _ in reversed(ref)]


def test_lru_rejects_bad_capacity():
    with pytest.raises(ValueError):
        LRUCache(0)


# ---- Top-k heap ---------------------------------------------------------------------------
def test_top_k_matches_sorting():
    rng = random.Random(1)
    items = [rng.random() if rng.random() > 0.1 else None for _ in range(2000)]
    for k in (1, 5, 50):
        expected = sorted((x for x in items if x is not None), reverse=True)[:k]
        assert top_k(items, k, key=lambda x: x) == expected
        assert top_k(items, k, key=lambda x: x, largest=False) == sorted(x for x in items if x is not None)[:k]


def test_top_k_ties_keep_input_order_and_edge_cases():
    items = [("a", 1), ("b", 3), ("c", 3), ("d", 2)]
    assert top_k(items, 2, key=lambda x: x[1]) == [("b", 3), ("c", 3)]
    assert top_k(items, 0, key=lambda x: x[1]) == []
    assert top_k([], 3, key=lambda x: x) == []


# ---- Token bucket -------------------------------------------------------------------------
def test_token_bucket_burst_then_refill():
    clock = FakeClock()
    b = TokenBucket(rate=2, capacity=3, clock=clock)
    assert [b.allow("x") for _ in range(4)] == [True, True, True, False]
    assert b.allow("y")  # buckets are per client
    assert b.retry_after("x") == pytest.approx(0.5)
    clock.t = 0.5  # one token refilled
    assert b.allow("x") and not b.allow("x")
    clock.t = 100
    assert sum(b.allow("x") for _ in range(10)) == 3  # never more than capacity
