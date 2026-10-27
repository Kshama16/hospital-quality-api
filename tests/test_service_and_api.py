import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.ds import TokenBucket
from app.main import create_app
from app.repositories import RepositoryError, SQLiteHospitalRepository
from app.resilience import CircuitBreaker
from app.service import HospitalService, ServiceUnavailable


class FailingRepo(SQLiteHospitalRepository):
    """Wraps SQLite; get() fails while `down` is True."""

    def __init__(self) -> None:
        super().__init__()
        self.down, self.get_calls = False, 0

    def get(self, provider_id):
        self.get_calls += 1
        if self.down:
            raise RepositoryError("timeout")
        return super().get(provider_id)


@pytest.fixture
def client(sample):
    repo = SQLiteHospitalRepository()
    repo.put_many(sample)
    with TestClient(create_app(Settings(), repo=repo)) as c:
        yield c


def test_get_search_list_rank(client):
    assert client.get("/hospitals/220071").json()["name"] == "Massachusetts General Hospital"
    assert client.get("/hospitals/999999").status_code == 404
    r = client.get("/hospitals/search", params={"q": "medical cent"}).json()
    assert [h["name"] for h in r["items"]] == ["Berkshire Medical Center", "Boston Medical Center"]
    assert client.get("/hospitals/search", params={"q": "x"}).status_code == 422
    r = client.get("/rankings/ed_median_minutes", params={"state": "ma", "k": 2}).json()
    assert [h["provider_id"] for h in r["items"]] == ["220031", "220046"] and r["higher_is_better"] is False
    r = client.get("/rankings/overall_rating", params={"k": 1}).json()
    assert r["items"][0]["provider_id"] == "220071"
    assert client.get("/rankings/nope").status_code == 422


def test_keyset_pagination_walks_every_row_once(client):
    seen, cursor = [], None
    while True:
        params = {"limit": 3, **({"cursor": cursor} if cursor else {})}
        page = client.get("/states/MA/hospitals", params=params).json()
        seen += [h["provider_id"] for h in page["items"]]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert seen == ["220031", "220046", "220071", "220110"]
    assert len(client.get("/states/MA/hospitals", params={"min_rating": 5}).json()["items"]) == 2


def test_health_metrics_and_request_id(client):
    client.get("/hospitals/220071")
    client.get("/hospitals/220071")
    r = client.get("/metrics", headers={"x-request-id": "abc"})
    assert r.headers["x-request-id"] == "abc"
    m = r.json()
    assert m["cache"]["hits"] >= 1 and m["routes"]["/hospitals/{provider_id}"]["requests"] == 2
    assert client.get("/health").json() == {"status": "ok", "circuit": "closed", "indexed_hospitals": 5}


def test_rate_limit_returns_429_with_retry_after(sample):
    repo = SQLiteHospitalRepository()
    repo.put_many(sample)
    with TestClient(create_app(Settings(), repo=repo, limiter=TokenBucket(rate=0.001, capacity=2))) as c:
        codes = [c.get("/hospitals/220071", headers={"x-api-key": "k1"}).status_code for _ in range(3)]
        assert codes == [200, 200, 429]
        assert c.get("/hospitals/220071", headers={"x-api-key": "k2"}).status_code == 200
        assert c.get("/health", headers={"x-api-key": "k1"}).status_code == 200  # health is never limited


def test_cache_serves_hits_and_breaker_fails_fast(sample):
    repo = FailingRepo()
    repo.put_many(sample)
    svc = HospitalService(repo, breaker=CircuitBreaker(failure_threshold=2, reset_timeout=60), sleep=lambda _: None)
    assert svc.get("220071").name == "Massachusetts General Hospital"
    repo.down = True
    assert svc.get("220071") is not None and repo.get_calls == 1  # served from cache
    for _ in range(2):
        with pytest.raises(ServiceUnavailable):
            svc.get("220110")  # 3 retries each
    assert repo.get_calls == 1 + 2 * 3 and svc.breaker.state == "open"
    with pytest.raises(ServiceUnavailable):
        svc.get("220031")
    assert repo.get_calls == 7  # open breaker: no call made


def test_api_returns_503_when_store_is_down(sample):
    repo = FailingRepo()
    repo.put_many(sample)
    repo.down = True
    with TestClient(create_app(Settings(), repo=repo)) as c:
        r = c.get("/hospitals/220071")
        assert r.status_code == 503 and r.headers["retry-after"] == "5"
