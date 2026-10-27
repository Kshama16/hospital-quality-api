"""Async load test against a running API: throughput and latency percentiles.

Usage: python scripts/load_test.py [BASE_URL] [REQUESTS] [CONCURRENCY]
Traffic mix: 70% hospital lookups (skewed to popular hospitals), 20% search, 10% rankings.
"""

import asyncio
import json
import math
import random
import sys
import time
from pathlib import Path

import httpx

SEED = Path(__file__).resolve().parents[1] / "data" / "hospitals.json"
IDS = [r["provider_id"] for r in json.loads(SEED.read_text())]
QUERIES = ["mass gen", "children", "saint mary", "univ med", "memorial", "kaiser", "mayo", "baptist"]
STATES = ["MA", "NY", "CA", "TX", "FL", "IL", "PA", "OH"]


def next_path(rng: random.Random) -> str:
    r = rng.random()
    if r < 0.7:
        return f"/hospitals/{IDS[min(int(rng.paretovariate(1.2)) - 1, len(IDS) - 1)]}"
    if r < 0.9:
        return f"/hospitals/search?q={rng.choice(QUERIES)}"
    return f"/rankings/ed_median_minutes?state={rng.choice(STATES)}&k=10"


async def main(base: str, n: int, concurrency: int) -> None:
    rng = random.Random(42)
    paths = [next_path(rng) for _ in range(n)]
    latencies: list[float] = []
    errors = 0
    queue: asyncio.Queue[str] = asyncio.Queue()
    for p in paths:
        queue.put_nowait(p)

    async def worker(client: httpx.AsyncClient) -> None:
        nonlocal errors
        while not queue.empty():
            path = queue.get_nowait()
            t = time.perf_counter()
            r = await client.get(path)
            latencies.append((time.perf_counter() - t) * 1000)
            errors += r.status_code >= 500

    limits = httpx.Limits(max_connections=concurrency)
    async with httpx.AsyncClient(base_url=base, limits=limits, timeout=30) as client:
        start = time.perf_counter()
        await asyncio.gather(*(worker(client) for _ in range(concurrency)))
        elapsed = time.perf_counter() - start
        cache = (await client.get("/metrics")).json()["cache"]
    s = sorted(latencies)
    pct = lambda p: s[max(1, math.ceil(p / 100 * len(s))) - 1]
    print(
        f"{n:,} requests, concurrency {concurrency}: {n / elapsed:,.0f} req/s, "
        f"p50 {pct(50):.1f} ms, p95 {pct(95):.1f} ms, p99 {pct(99):.1f} ms, 5xx errors {errors}, "
        f"cache hit rate {cache['hit_rate']:.1%}"
    )


if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 5000
    concurrency = int(sys.argv[3]) if len(sys.argv) > 3 else 50
    asyncio.run(main(base, n, concurrency))
