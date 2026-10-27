import pytest

from app.resilience import CircuitBreaker, CircuitOpenError, retry


class Flaky:
    def __init__(self, failures: int) -> None:
        self.failures, self.calls = failures, 0

    def __call__(self) -> str:
        self.calls += 1
        if self.calls <= self.failures:
            raise ConnectionError("boom")
        return "ok"


def test_retry_succeeds_after_transient_failures_with_backoff():
    sleeps: list[float] = []
    fn = Flaky(2)
    assert retry(fn, attempts=3, base_delay=0.1, sleep=sleeps.append) == "ok"
    assert fn.calls == 3 and len(sleeps) == 2
    assert 0 <= sleeps[0] <= 0.1 and 0 <= sleeps[1] <= 0.2  # full jitter, doubling cap


def test_retry_gives_up_and_only_retries_listed_errors():
    with pytest.raises(ConnectionError):
        retry(Flaky(5), attempts=3, sleep=lambda _: None)
    fn = Flaky(1)
    with pytest.raises(ConnectionError):
        retry(fn, retry_on=(TimeoutError,), sleep=lambda _: None)
    assert fn.calls == 1


def test_circuit_breaker_opens_half_opens_and_closes():
    t = [0.0]
    cb = CircuitBreaker(failure_threshold=2, reset_timeout=10, clock=lambda: t[0])
    for _ in range(2):
        with pytest.raises(ConnectionError):
            cb.call(Flaky(1))
    assert cb.state == "open"
    with pytest.raises(CircuitOpenError):
        cb.call(lambda: "never called")
    t[0] = 10
    assert cb.state == "half_open"
    with pytest.raises(ConnectionError):  # failed trial call reopens
        cb.call(Flaky(1))
    assert cb.state == "open"
    t[0] = 20
    assert cb.call(lambda: "ok") == "ok" and cb.state == "closed"
