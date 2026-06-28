# Rate-Tracker

A production-shaped service that ingests interest-rate data, persists it,
exposes it via a typed/cached REST API, refreshes it on a schedule, and renders
it in a live dashboard.

```
parquet/HTTP source -> ingestion worker -> PostgreSQL -> DRF API (Redis cache) -> Next.js dashboard
                                  \-> Celery Beat refreshes on a schedule
```

## Stack

| Layer        | Tech                                              |
| ------------ | ------------------------------------------------- |
| API          | Django 5 + Django REST Framework                  |
| Database     | PostgreSQL 16 (migrations only, no raw SQL)       |
| Cache/broker | Redis 7 (`django-redis` + Celery)                 |
| Scheduling   | Celery worker + Celery Beat (DB scheduler)        |
| Ingestion    | `pyarrow` streaming parquet loader + HTTP scraper |
| Frontend     | Next.js 14 + TailwindCSS + Recharts               |
| Runtime      | Docker Compose, Python 3.12, Node 20              |
| Deployment   | Docker Compose (local), AWS ECS (production)      |

## Quickstart

```bash
make env          # create .env from .env.example
make up           # build + start db, redis, web, worker, beat, frontend
make seed         # load rates_seed.parquet (~1M rows) idempotently
make test         # run the backend test suite
make logs         # tail all logs
```

- API: http://localhost:8000 (health: `/health`)
- Dashboard: http://localhost:3000

## Endpoints

| Method | Path             | Auth   | Notes                                                                       |
| ------ | ---------------- | ------ | --------------------------------------------------------------------------- |
| GET    | `/rates/latest`  | public | Latest rate per provider; `?rate_type=` filter; Redis-cached (60s)          |
| GET    | `/rates/history` | public | Historical rates; `?provider=&rate_type=`; last 30 days; Redis-cached (60s) |
| POST   | `/rates/ingest`  | bearer | Validated webhook; upserts + invalidates cache                              |

## Features

- **Idempotent ingestion:** Seed file and webhook use the same upsert logic; re-running is safe.
- **Data quality:** Provider canonicalization (slug), currency normalization, and quarantine of invalid rows.
- **Observability:** Structured JSON logging, slow-query warnings (>200ms), and Celery task visibility.
- **Fast startup:** Streams full dataset in 50k batches with live progress bar; dashboard loads immediately while data ingests in background.
- **Responsive dashboard:** Table + chart, 60s auto-refresh, loading/error states, mobile-friendly.

## Documentation

- `DECISIONS.md` — running log of choices, assumptions, tradeoffs, and future changes.
- `schema.md` — database design, indexes, and the queries they serve.
- `docs/aws-deployment.md` — comprehensive AWS ECS deployment guide with architecture diagram.

## Environment

Copy `.env.example` to `.env`. The app **fails fast** at startup if a required
variable is missing. No secrets are committed.

Key variables:

- `DJANGO_SECRET_KEY` — Django secret key (generate with `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`)
- `POSTGRES_*` — PostgreSQL connection settings
- `REDIS_URL` / `CELERY_BROKER_URL` — Redis for cache and Celery
- `INGEST_API_TOKEN` — Bearer token for `POST /rates/ingest`
- `SCRAPE_INTERVAL_SECONDS` — How often the scheduled scrape runs (default: 300)

## Testing

```bash
make test         # run backend tests (pytest)
make test-cleaning  # run cleaning unit tests only
make test-api    # run API tests (requires Docker)
```

Tests cover:

- Data cleaning and canonicalization (`test_cleaning.py`)
- API endpoints with caching and auth (`test_api.py`)
- Note: API tests require Postgres (run in Docker, not locally)

## Management Commands

```bash
# Seed data from parquet (idempotent)
docker compose exec web python manage.py seed_data --path /app/rates_seed.parquet

# Sample N rows for fast testing
docker compose exec web python manage.py seed_data --sample 1000

# Replay failed raw responses after fixing bugs
docker compose exec web python manage.py replay_failed --limit 100
```

## Deployment

### Local Development

```bash
make up           # start all services with Docker Compose
```

### Production (AWS ECS)

See `docs/aws-deployment.md` for complete deployment guide including:

- AWS resource setup (ECR, ECS, RDS, ElastiCache, ALB, S3)
- GitHub Actions CI/CD workflow
- Task definitions for web, frontend, worker, and beat services
- Architecture diagram and troubleshooting guide

## AI Tools Used

- **Cursor IDE** - Primary development environment
- **Using Superpowers** - Brainstorming and planning workflows
- **Caveman** - Token compression for efficient communication
- **RTK-TDD** - Test-driven development discipline for code
- **code-review-graph** - Knowledge graph for codebase context and impact analysis
