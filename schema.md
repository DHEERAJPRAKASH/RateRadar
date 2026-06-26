# Database Schema

Tables, indexes, and the queries they serve. No raw SQL dumps — all changes are via Django migrations.

## Tables

### `Provider`

Dimension table for rate publishers (banks). The `slug` is the canonicalization/dedup key used during ingestion to collapse dirty variants (e.g. `hsbc`/`Hsbc`/`HSBC` → `hsbc`). The `name` holds the curated display name.

| Column | Type | Notes |
|--------|------|-------|
| `id` | BigAutoField | Primary key |
| `name` | CharField(255) | Unique, human-readable display name |
| `slug` | SlugField(255) | Unique, canonicalization key (`slugify(name.lower().strip())`) |
| `created_at` | DateTimeField | Auto, row creation time |

**Indexes:** none (small cardinality, unique constraints suffice).

### `RawResponse`

Audit + replay store. Captures the original pre-clean payload so quarantined rows can be re-processed after a fix without re-fetching.

| Column | Type | Notes |
|--------|------|-------|
| `id` | BigAutoField | Primary key |
| `external_id` | CharField(128) | Source-provided id (parquet `raw_response_id`), unique/nullable |
| `source_url` | URLField(512) | Where the payload came from |
| `payload` | JSONField | Original pre-clean row/HTTP body |
| `status` | CharField(16) | `parsed` or `failed` |
| `parse_error` | TextField | Reason text if `status=failed` |
| `fetched_at` | DateTimeField | When the source was fetched (nullable) |
| `created_at` | DateTimeField | Auto, row creation time |

**Indexes:**
- `ix_raw_status` on `status` — filter for replay (`status=failed`).
- `ix_raw_created_at` on `created_at` — time-window queries.

### `Rate`

Cleaned fact table. One observation per provider/type/effective day (natural key). The `ingestion_ts` is the source-claimed timestamp; `created_at` is our DB write time.

| Column | Type | Notes |
|--------|------|-------|
| `id` | BigAutoField | Primary key |
| `provider` | ForeignKey(Provider) | PROTECT, related_name `rates` |
| `rate_type` | CharField(64) | e.g. `savings_1yr_fixed`, `30yr_fixed_mortgage` |
| `rate_value` | DecimalField(7,4) | Float64→Decimal to avoid drift |
| `currency` | CharField(8) | Normalized ISO code (e.g. `USD`) |
| `effective_date` | DateField | The date the rate is effective |
| `ingestion_ts` | DateTimeField | Source-claimed ingestion timestamp |
| `source_url` | URLField(512) | Source URL |
| `raw_response` | ForeignKey(RawResponse) | SET_NULL, related_name `rates` |
| `created_at` | DateTimeField | Auto, our DB write time |

**Constraints:**
- `uq_rate_natural_key` — `UniqueConstraint(provider, rate_type, effective_date)`. At most one observation per bank/type/day. Re-ingests upsert (latest `ingestion_ts` wins).

**Indexes:**
- `ix_rate_provider_type_eff` — `(provider, rate_type, -effective_date, -ingestion_ts)`. Serves filtered "latest per provider" and provider+type history.
- `ix_rate_provider_eff` — `(provider, -effective_date, -ingestion_ts)`. Serves unfiltered "latest per provider" via `DISTINCT ON (provider)`.
- `ix_rate_type_eff` — `(rate_type, effective_date)`. Serves "rate change over last 30 days for a given type".
- `ix_rate_ingestion_ts` — `(ingestion_ts)`. Serves "records ingested in a 24-hour window".

## Required Queries

### 1. Latest rate per provider

```sql
SELECT DISTINCT ON (provider_id) *
FROM rates_rate
ORDER BY provider_id, effective_date DESC, ingestion_ts DESC;
```

**Index used:** `ix_rate_provider_eff` (`provider, -effective_date, -ingestion_ts`). The `DISTINCT ON` clause leverages the ordering to pick the first row per provider (latest by `effective_date`, tie-break by `ingestion_ts`).

With optional `type` filter:

```sql
SELECT DISTINCT ON (provider_id) *
FROM rates_rate
WHERE rate_type = %s
ORDER BY provider_id, effective_date DESC, ingestion_ts DESC;
```

**Index used:** `ix_rate_provider_type_eff` (`provider, rate_type, -effective_date, -ingestion_ts`). The leading `provider` and `rate_type` columns support the filter and ordering.

### 2. Rate change over the last 30 days for a given type

```sql
SELECT *
FROM rates_rate
WHERE rate_type = %s
  AND effective_date >= NOW() - INTERVAL '30 days'
ORDER BY effective_date DESC;
```

**Index used:** `ix_rate_type_eff` (`rate_type, effective_date`). The index supports the `rate_type` equality filter and the `effective_date` range scan.

### 3. All records ingested in a given 24-hour window

```sql
SELECT *
FROM rates_rate
WHERE ingestion_ts >= %s
  AND ingestion_ts < %s
ORDER BY ingestion_ts DESC;
```

**Index used:** `ix_rate_ingestion_ts` (`ingestion_ts`). The index supports the range scan on `ingestion_ts`.

## Tradeoffs

- **`rate_type` is denormalized.** A dimension table was considered but rejected given the small, stable set of types (5 from EDA) and the 48-hour window. The CharField is indexed and documented.
- **`created_at` vs `ingestion_ts`.** Two timestamps exist: `ingestion_ts` (source-claimed, used for recency/tie-breaking) and `created_at` (our DB write time, used for audit). This is intentional; the brief asks for ingestion timestamp in the data model.
- **Partitioning deferred.** 1M rows is small for PostgreSQL. Future scaling would use declarative monthly partitioning on `effective_date`.
- **DecimalField(7,4).** Float64→Decimal to avoid drift on financial values. 7 digits total, 4 decimal places (e.g. `12.3456`). If rates exceed 999.9999%, increase precision.
