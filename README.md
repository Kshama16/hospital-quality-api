# Hospital Quality API

**Portfolio project | Backend / cloud software engineering**

A REST microservice for public CMS hospital quality data on 5,419 US hospitals. It supports lookup by ID, name autocomplete, state listings with pagination, and top-k rankings. The project covers the parts of a production service beyond the endpoints:

- **Data structures I implemented myself:** a trie, an LRU cache, a heap for top-k and a token-bucket rate limiter.
- **Interchangeable storage:** a repository interface with **SQL (SQLite)** and **NoSQL (Amazon DynamoDB)** implementations.
- **Fault tolerance:** retries with exponential backoff and a **circuit breaker**.
- **Observability:** request metrics, plus CloudWatch-format logs and alarms.
- **AWS deployment:** an **AWS SAM** template for Lambda, API Gateway and DynamoDB.
- **CI/CD** with GitHub Actions.

```
client ─► API Gateway (HTTP API) ─► Lambda (FastAPI via Mangum) ─► DynamoDB
                                        │
          middleware: request ID, token-bucket rate limit (429), timing, EMF logs → CloudWatch alarms
                                        │
          HospitalService: LRU cache ─► retry + circuit breaker ─► HospitalRepository (interface)
                           trie index, heap top-k                    ├─ DynamoDBHospitalRepository
                                                                     └─ SQLiteHospitalRepository
```

## Endpoints

| Method & path | What it does |
|---|---|
| `GET /hospitals/{provider_id}` | One hospital (cache-aside read) |
| `GET /hospitals/search?q=mass gen` | Autocomplete: every query word must prefix a word in the name or city (trie) |
| `GET /states/{state}/hospitals?min_rating=4&limit=20&cursor=…` | State listing with keyset pagination |
| `GET /rankings/{metric}?state=MA&k=10` | Top-k hospitals by star rating, patient experience, sepsis care, ED wait time or infection ratio (heap) |
| `GET /health`, `GET /metrics` | Liveness, circuit state, per-route request counts and p50/p95/p99 latency, cache hit rate |

## Design notes

| Component | Implementation | Complexity |
|---|---|---|
| `app/ds/trie.py` | Prefix tree; each node stores the IDs that pass through it, so a lookup never walks the subtree. Multi-word queries intersect the sets. | insert O(L), lookup O(P) |
| `app/ds/lru_cache.py` | Hash map + doubly linked list, TTL, thread-safe, hit/miss/eviction counters | get/put O(1) |
| `app/ds/top_k.py` | Bounded binary min-heap with manual sift-up/sift-down | O(n log k) time, O(k) memory |
| `app/ds/rate_limiter.py` | Token bucket for each API key: allows bursts while capping the sustained rate | O(1) per request |
| `app/resilience.py` | Retry with exponential backoff and full jitter; circuit breaker (closed → open → half-open) | |
| `app/repositories/` | Abstract `HospitalRepository`. SQLite version: parameterized SQL with a (state, provider_id) index. DynamoDB version: single-table design, a GSI on state, `LastEvaluatedKey` pagination, batch writes. | |

**Failure behavior:** a failed data-store call is retried three times with backoff. After five consecutive failures the circuit opens, so requests fail fast with `503` and `Retry-After` instead of piling onto a struggling dependency. After 30 seconds one trial call is allowed through, and a success closes the circuit again. Cached hospitals keep being served throughout.

## Quality

| Check | Result |
|---|---|
| Unit and integration tests (pytest) | 26 passing, 98% line coverage |
| Contract tests | The same suite runs against SQLite and against DynamoDB (mocked with moto), including a pagination test that spans more than one DynamoDB page |
| Property-style tests | The LRU cache matches a reference model over 5,000 random operations. Top-k matches full sorting. Trie search matches brute force on all 5,419 real names. |
| Lint, format, types | ruff, ruff format, mypy: clean |
| Infrastructure | `cfn-lint` validates the SAM template |
| CI/CD | GitHub Actions runs lint, types, tests (coverage gate 90%) and template validation on Python 3.12 and 3.13; a deploy job runs `sam deploy` on `main` once AWS credentials are configured |

**Load test** (`scripts/load_test.py`, mixed traffic, local server on an 8-core laptop that also runs the load generator):

| Setup | Throughput | p50 | p95 | p99 | 5xx errors |
|---|---|---|---|---|---|
| 1 worker, 1 client | 1,097 req/s | 0.9 ms | 1.0 ms | 1.1 ms | 0 |
| 4 workers, 8 concurrent clients | 1,576 req/s | 4.0 ms | 10.4 ms | 19.3 ms | 0 |

Server-side handling time is under 1 ms at p95 on every route, measured by the app's own middleware. The cache hit rate is about 98% on the skewed traffic mix.

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/uvicorn app.main:app --reload          # SQLite in memory, seeded from data/hospitals.json
curl "localhost:8000/hospitals/search?q=mass%20gen"
curl "localhost:8000/rankings/sepsis_care_pct?state=MA&k=5"
.venv/bin/pytest --cov=app                       # tests
.venv/bin/ruff check . && .venv/bin/mypy app     # lint and types
```

**Deploy to AWS** (requires the AWS SAM CLI and an AWS account):

```bash
sam build --template infra/template.yaml && sam deploy --guided
python scripts/load_dynamodb.py hospital-quality-dev     # load the 5,419 hospitals
```

The template creates a DynamoDB table (on-demand, point-in-time recovery), a Lambda function (arm64, X-Ray tracing, read-only IAM policy), an HTTP API with throttling, a log group with 30-day retention, and CloudWatch alarms on Lambda errors and on p95 latency, which comes from the Embedded Metric Format logs the app writes.

## Data

`scripts/build_seed.py` builds `data/hospitals.json` from the CMS Provider Data Catalog (public, no patient data): Hospital General Information, Timely and Effective Care (OP_18b, SEP_1), the HCAHPS summary star rating, and the average standardized infection ratio across HAI measures.

---

Built by [Kshama Upadhyay](https://github.com/Kshama16). Related: [healthcare-data-integration-spark](https://github.com/Kshama16/healthcare-data-integration-spark) (Spark/Hive ETL on the same CMS sources).
