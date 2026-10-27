"""In-process request metrics for /metrics, plus CloudWatch Embedded Metric Format log lines."""

from __future__ import annotations

import json
import math
import threading
import time
from collections import defaultdict, deque


def percentile(sorted_values: list[float], p: float) -> float:
    """Nearest-rank percentile of an already sorted list."""
    if not sorted_values:
        return 0.0
    rank = max(1, math.ceil(p / 100 * len(sorted_values)))
    return sorted_values[rank - 1]


class Metrics:
    def __init__(self, window: int = 2048) -> None:
        self._lock = threading.Lock()
        self._latency: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=window))
        self._status: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
        self.started = time.time()

    def record(self, route: str, status: int, latency_ms: float) -> None:
        with self._lock:
            self._latency[route].append(latency_ms)
            self._status[route][status] += 1

    def snapshot(self) -> dict:
        with self._lock:
            routes = {}
            for route, lat in self._latency.items():
                s = sorted(lat)
                codes = self._status[route]
                total = sum(codes.values())
                routes[route] = {
                    "requests": total,
                    "errors_5xx": sum(n for c, n in codes.items() if c >= 500),
                    "throttled_429": codes.get(429, 0),
                    "latency_ms": {
                        "p50": round(percentile(s, 50), 3),
                        "p95": round(percentile(s, 95), 3),
                        "p99": round(percentile(s, 99), 3),
                    },
                }
            return {"uptime_seconds": round(time.time() - self.started, 1), "routes": routes}


def emf_log(route: str, status: int, latency_ms: float, request_id: str) -> str:
    """One JSON log line that CloudWatch turns into Latency and Errors metrics automatically."""
    return json.dumps(
        {
            "_aws": {
                "Timestamp": int(time.time() * 1000),
                "CloudWatchMetrics": [
                    {
                        "Namespace": "HospitalQualityApi",
                        "Dimensions": [["route"]],
                        "Metrics": [{"Name": "Latency", "Unit": "Milliseconds"}, {"Name": "Errors", "Unit": "Count"}],
                    }
                ],
            },
            "route": route,
            "status": status,
            "request_id": request_id,
            "Latency": round(latency_ms, 3),
            "Errors": int(status >= 500),
        }
    )
