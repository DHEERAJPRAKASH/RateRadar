# DECISIONS

A running log of significant engineering decisions, assumptions, and the
tradeoffs considered. Newest entries are appended as the build progresses.

## Philosophy

- **Walking skeleton first.** Get `docker-compose up` green with a health check
  before adding features, so integration risk surfaces early.
- **Idempotency and observability are first-class**, wired in from the start —
  not retrofitted.
- **Fail fast on misconfiguration.** A missing env var aborts startup with a
  clear message rather than crashing mid-request.

## Platform / runtime

- **Python 3.12 in Docker** (host runs 3.14). 3.14 lacks reliable wheels for
  `pyarrow`/`psycopg`; everything runs in containers so the host version is
  irrelevant. Local tests can run on 3.10–3.13.
- **PostgreSQL 16** — the schema relies on `DISTINCT ON` and `ON CONFLICT`
  (native upsert), both PostgreSQL features.
- **Redis 7** does double duty as the Django cache backend _and_ the Celery
  broker/result backend — one dependency, two needs.

## Scheduling: Celery Beat over cron

Chosen Celery + `django-celery-beat` because:

- Redis is already required for caching, so it doubles as the broker — no new
  infra.
- First-class retries/backoff, visibility into task state, and the same code
  path can be triggered ad-hoc (`run_scrape`) or on a schedule.
- The DB-backed scheduler keeps the schedule editable and durable across
  restarts.
- Tradeoff: more moving parts (worker + beat) than a single cron container.
  Justified by the observability/retry story the assessment asks for.

## Configuration & secrets

- All config is read through `common.env.get_required_env`, the single
  fail-fast choke point. `.env.example` documents every variable.
- The ingest endpoint is guarded by a **static bearer token** from
  `INGEST_API_TOKEN` (no external auth service, per the brief). A per-user DRF
  `TokenAuthentication` model was considered but rejected as overkill for a
  single webhook producer.

<!-- Phase 1B/1A/2/3 decisions appended below as implemented. -->

## Data model & canonicalization

- **Provider slug as canonical key.** The EDA revealed dirty provider names (e.g. `hsbc`/`Hsbc`/`HSBC`). We canonicalize via `slugify()` and store a curated display name in a dimension table. This collapses duplicates at ingestion time without a separate normalization service.
- **Currency normalization.** Only ISO codes are accepted (USD/EUR/GBP). Variants like `US Dollar` are quarantined. This is stricter than a fuzzy matcher but keeps the pipeline simple and predictable.
- **Quarantine over silent drop.** Invalid rows are stored in `RawResponse` with `status=FAILED` and a reason. This enables replay after fixing bugs without re-fetching, which the brief explicitly asked for.
- **Natural key upsert.** The `Rate` table has a unique constraint on `(provider, rate_type, effective_date)`. Re-ingests update the row (latest `ingestion_ts` wins). This supports corrections and idempotency without duplicate rows.

## Idempotency strategy

- **Seed ingestion:** The `seed_data` command streams the parquet file in batches, cleans each row, and upserts via Django's `bulk_create(update_conflicts=True)`. Running the command multiple times is a no-op if data hasn't changed.
- **Webhook ingestion:** `POST /rates/ingest` uses the same upsert logic. Sending the same payload twice updates rows but doesn't create duplicates.
- **Scraping:** The Celery task fetches, parses, and upserts. If the source returns the same data, the upsert is a no-op (same values).
- **Cache invalidation:** After successful ingest, we delete the `rates:latest:all` cache key. History keys rely on TTL (60s) since pattern deletion isn't supported by Django's cache abstraction.

## Boot seeding: async full seed + live progress

- **Inline sample replaced by an async full seed.** `entrypoint.sh` now runs
  `manage.py seed_data --async`, which enqueues the `seed_full_data` Celery task
  instead of blocking boot on an inline sample. The web service comes up
  immediately; the worker streams the full parquet in 50k-row batches.
- **Idempotent and guarded.** `seed_full_data` returns early (marking the job
  `complete`) if `Rate` rows already exist, so re-running `docker compose up`
  stays fast and never double-seeds.
- **Streaming, not full-load.** `stream_seed` uses `pyarrow.iter_batches` so the
  ~1M rows never sit in memory at once. The same function backs both the
  management command and the Celery task (one code path, two entry points).
- **Live progress via a Redis status key.** Progress is published after each
  batch to the `ingestion:status` cache key (`state`, `total`, `processed`,
  `inserted`, `updated`, `output`, `quarantined`, timestamps, `error`). It has no
  TTL — it is a live job marker, not a cache entry. `GET /ingestion/status`
  exposes it and the dashboard polls it (2s while running, backing off to 15s
  once settled) to drive the progress bar.

## Read API surface: browse, quarantine, meta

- **On-demand browse endpoint.** The brief asked for filtering the stored data;
  the dashboard had no controls for it. Added `GET /rates/browse` supporting
  `rate_type`, `provider`, and `from`/`to` date filters, served via
  `select_related("provider")` to avoid N+1 queries.
- **Bounded pagination everywhere.** `DefaultPagination` (`page_size=50`,
  `max_page_size=500`) ensures browse/quarantine endpoints never return an
  unbounded result set, even against the full ~1M-row table.
- **Quarantine visibility.** `GET /rates/quarantined` lists `RawResponse` rows
  with `status=FAILED` and their parse reason, so bad data is inspectable (and
  replayable) from the UI rather than buried in logs.
- **Filter metadata endpoint.** `GET /rates/meta` returns the distinct
  `rate_types` and the `providers` list so the frontend can populate filter
  dropdowns without hardcoding values or scanning the fact table client-side.

## Frontend: TanStack Query + on-demand filters

- **TanStack Query for server state.** A `providers.tsx` QueryClient wraps the
  app; typed hooks in `lib/queries.ts` wrap a typed client in `lib/api.ts`.
  Auto-refresh is 60s for rate data, with faster polling for the live seed.
- **Filter-driven dashboard.** `FilterBar` (date range, rate type, provider)
  feeds `AllRatesTable` (paginated browse), alongside `LatestRatesTable`,
  `HistoryChart`, `QuarantineTable`, and `IngestionProgress`. This delivers the
  "explore the data on demand" requirement the original UI lacked.
- **Shared loading/error UX.** A `QueryState` wrapper standardizes
  loading/error/empty states across components instead of repeating the logic.

## Testing strategy: mocked-HTTP scraper

- **No real network in tests.** `test_scraper_mock.py` uses the `responses`
  library to intercept HTTP, asserting fetch→parse matches a known fixture and
  that failures (timeout, 4xx, empty body, invalid JSON) surface as typed errors
  and are quarantined — proving the worker never crashes silently, as the brief
  requires.

## Ingestion metrics: inserted vs updated vs output

- **Problem.** The dashboard showed `Inserted: 464,278` while `All Rates` showed
  only `27,434` rows, which looked like data loss. It was not. The seed reads
  ~1M rows in 50k batches; `_dedupe_by_natural_key` only dedupes *within* a
  batch, so the same `(provider, rate_type, effective_date)` key recurs across
  batches and is resolved by the `bulk_create(update_conflicts=True)` upsert as
  an **UPDATE**, not an INSERT. The old counter set
  `result.inserted = len(rate_objs)`, counting every upsert (insert + update) as
  an insert and summing it across batches.
- **Fix.** `_upsert_rates` now derives real counts from the table-size delta:
  `inserted = count(after) - count(before)` and
  `updated = len(rate_objs) - inserted`. Django's `bulk_create(update_conflicts)`
  does not report per-row insert/update outcomes, so the count delta is the
  cheapest accurate signal (two `COUNT(*)` per batch; negligible at ~20 batches).
- **Surfaced metrics.** The ingestion status now publishes three distinct
  numbers — `inserted` (new rows), `updated` (re-ingested corrections), and
  `output` (distinct rows now in the table) — wired through `tasks.py` and
  rendered in `IngestionProgress`. They reconcile as
  `upserts = inserted + updated` and `output == inserted` for a from-empty seed.
  Example: `1,005,000 read − 231 quarantined → 464,278 upserts =
  27,434 inserted + 436,844 updated → output 27,434`, which matches `All Rates`.
- **Tradeoff.** The count-delta approach assumes no concurrent writers during a
  batch. Acceptable for the single-worker seed and the serialized webhook path;
  a concurrent ingest would skew the split (not the total).

## Assumptions made

1. **Seed file schema is stable.** The parquet file has 8 columns: `provider`, `rate_type`, `rate_value`, `currency`, `effective_date`, `ingestion_ts`, `source_url`, `raw_response_id`. We assume this schema won't change during the assessment.
2. **Single currency (USD) dominates.** The EDA showed mostly USD. We normalize to ISO codes but don't build multi-currency conversion logic.
3. **Rate types are a small, stable set.** The EDA found ~5 types. We store them as a denormalized string rather than a dimension table to keep the 48-hour scope manageable.
4. **Dashboard availability SLA is 2 minutes.** The page must be usable quickly. We now enqueue the **full** parquet seed as a background Celery task on boot (no inline sample). The page loads immediately and a progress bar polls `/ingestion/status` while the worker streams the ~1M rows. (Superseded the earlier 5000-row inline auto-sample — see "Boot seeding".)
5. **PostgreSQL is available.** The schema uses `DISTINCT ON` and `ON CONFLICT`, which are PostgreSQL-specific. Porting to MySQL would require schema changes.
6. **Redis is single-node.** We don't configure Redis Sentinel or clustering. For a production deployment, this would be a single point of failure.

## Tradeoffs considered

- **Celery Beat vs cron.** Chose Celery Beat for observability, retries, and DB-backed schedule editing. Tradeoff: more moving parts (worker + beat) than a single cron container.
- **DecimalField vs FloatField.** Chose `DecimalField(7,4)` for financial precision. Tradeoff: slightly slower arithmetic and larger storage than float, but avoids drift on repeated calculations.
- **Parquet streaming vs full load.** Chose streaming with pyarrow to handle 1M rows without OOM. Tradeoff: more complex code than `pd.read_parquet()`, but necessary for production-scale ingestion.
- **Cache pattern deletion vs TTL.** Django's cache abstraction doesn't support pattern deletion. We delete known keys on ingest and rely on TTL for others. Tradeoff: stale cache for some history keys after ingest, but acceptable for the 60s TTL.
- **Static bearer token vs DRF TokenAuthentication.** Chose static token for simplicity (single webhook producer). Tradeoff: no per-user token revocation, but sufficient for the assessment scope.
- **Async full seed vs inline sample on startup.** Originally an inline 5000-row sample met the 2-minute SLA but showed partial, misleading data. Reversed to an **async full seed** (Celery) with a live progress bar: the page is usable immediately and the real ~1M-row dataset streams in the background. Tradeoff: requires the worker to be up and a status channel (Redis) to report progress, but the dashboard reflects the true dataset instead of an arbitrary sample.

## Future changes

1. **Partitioning.** With 1M rows and daily ingestion, the `Rate` table should be partitioned by `effective_date` (monthly partitions) to keep query performance stable.
2. **Cache pattern deletion.** Switch to a Redis client that supports `KEYS`/`SCAN` for pattern-based cache invalidation, or use cache tags.
3. **Multi-currency support.** Add a `Currency` dimension table and conversion rates if the product expands beyond USD.
4. **Rate type dimension.** If the number of rate types grows beyond ~20, normalize to a dimension table with metadata (e.g. term length, compounding frequency).
5. **Scalable scraping.** The current scraper iterates sources sequentially. For 100+ sources, implement parallel scraping with Celery groups or a dedicated fetcher service.
6. **Auth upgrade.** Replace the static bearer token with JWT or OAuth2 if the webhook producer needs per-client tokens or rate limiting.
7. **Frontend SSG.** Consider static generation for the dashboard if the data changes infrequently, reducing load on the API.
8. **Observability upgrade.** Add structured logging correlation IDs (request ID spans across services) and metrics export (Prometheus) for production monitoring.
9. **Exact insert/update counts.** The count-delta split is accurate only without concurrent writers. For exact per-row outcomes under concurrency, switch to raw SQL `INSERT ... ON CONFLICT ... RETURNING (xmax = 0) AS inserted` and tally the flag instead of diffing `COUNT(*)`.
