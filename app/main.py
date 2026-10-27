"""FastAPI application: routes, request-ID and timing middleware, rate limiting, error handling."""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from app.config import Settings
from app.ds import TokenBucket
from app.metrics import Metrics, emf_log
from app.models import METRICS, Hospital, HospitalPage, Ranking, SearchResult
from app.repositories import DynamoDBHospitalRepository, HospitalRepository, SQLiteHospitalRepository
from app.service import HospitalService, ServiceUnavailable

log = logging.getLogger("hospital_api")
logging.basicConfig(level=logging.INFO, format="%(message)s")


def build_repository(settings: Settings) -> HospitalRepository:
    if settings.repository == "dynamodb":
        return DynamoDBHospitalRepository(settings.table_name, settings.aws_region)
    repo = SQLiteHospitalRepository(settings.sqlite_path)
    if repo.count() == 0 and settings.seed_file.exists():
        repo.put_many(Hospital(**r) for r in json.loads(settings.seed_file.read_text()))
    return repo


def create_app(
    settings: Settings | None = None, repo: HospitalRepository | None = None, limiter: TokenBucket | None = None
) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        repository = repo or build_repository(settings)
        app.state.service = HospitalService(repository, settings.cache_size, settings.cache_ttl)
        yield

    app = FastAPI(
        title="Hospital Quality API",
        version="1.0.0",
        lifespan=lifespan,
        description="CMS hospital quality data: lookup, search, state listings and rankings.",
    )
    app.state.metrics = Metrics()
    app.state.limiter = limiter or TokenBucket(settings.rate_per_second, settings.rate_burst)

    @app.middleware("http")
    async def observe(request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        client = request.headers.get("x-api-key") or (request.client.host if request.client else "anon")
        start = time.perf_counter()
        if request.url.path not in ("/health", "/metrics") and not app.state.limiter.allow(client):
            response = JSONResponse(
                {"detail": "rate limit exceeded"},
                status_code=429,
                headers={"Retry-After": f"{app.state.limiter.retry_after(client):.2f}"},
            )
        else:
            response = await call_next(request)
        latency_ms = (time.perf_counter() - start) * 1000
        route = request.scope.get("route")
        route_path = getattr(route, "path", request.url.path)
        app.state.metrics.record(route_path, response.status_code, latency_ms)
        log.info(emf_log(route_path, response.status_code, latency_ms, request_id))
        response.headers["x-request-id"] = request_id
        return response

    @app.exception_handler(ServiceUnavailable)
    async def unavailable(_: Request, exc: ServiceUnavailable) -> JSONResponse:
        return JSONResponse(
            {"detail": "data store unavailable, retry later"}, status_code=503, headers={"Retry-After": "5"}
        )

    def svc(request: Request) -> HospitalService:
        return request.app.state.service

    @app.get("/health")
    def health(request: Request) -> dict:
        s = svc(request)
        return {"status": "ok", "circuit": s.breaker.state, "indexed_hospitals": s.trie.size}

    @app.get("/metrics")
    def metrics(request: Request) -> dict:
        s = svc(request)
        snap = request.app.state.metrics.snapshot()
        snap["cache"] = {
            "size": len(s.cache),
            "hit_rate": round(s.cache.hit_rate, 4),
            "hits": s.cache.hits,
            "misses": s.cache.misses,
            "evictions": s.cache.evictions,
        }
        snap["circuit"] = s.breaker.state
        return snap

    @app.get("/hospitals/search", response_model=SearchResult)
    def search(
        request: Request, q: str = Query(min_length=2, max_length=100), limit: int = Query(10, ge=1, le=50)
    ) -> SearchResult:
        items = svc(request).search(q, limit)
        return SearchResult(query=q, count=len(items), items=items)

    @app.get("/hospitals/{provider_id}", response_model=Hospital)
    def get_hospital(request: Request, provider_id: str) -> Hospital:
        h = svc(request).get(provider_id)
        if h is None:
            raise HTTPException(404, f"hospital {provider_id} not found")
        return h

    @app.get("/states/{state}/hospitals", response_model=HospitalPage)
    def list_hospitals(
        request: Request,
        state: str,
        min_rating: int | None = Query(None, ge=1, le=5),
        limit: int = Query(20, ge=1, le=100),
        cursor: str | None = None,
    ) -> HospitalPage:
        items, nxt = svc(request).list_state(state.upper(), min_rating, limit, cursor)
        return HospitalPage(items=items, next_cursor=nxt)

    @app.get("/rankings/{metric}", response_model=Ranking)
    def ranking(request: Request, metric: str, state: str | None = None, k: int = Query(10, ge=1, le=100)) -> Ranking:
        if metric not in METRICS:
            raise HTTPException(422, f"metric must be one of {sorted(METRICS)}")
        st = state.upper() if state else None
        return Ranking(
            state=st, metric=metric, higher_is_better=METRICS[metric], items=svc(request).rank(metric, k, st)
        )

    return app


app = create_app()
