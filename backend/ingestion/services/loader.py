"""Shared upsert logic for ingestion.

Used by ``seed_data``, the scraper, and ``POST /rates/ingest``. Handles:
- Provider resolution via canonical slug cache.
- RawResponse upsert (parsed + failed).
- Rate upsert with natural-key conflict resolution (latest ``ingestion_ts`` wins).
- In-batch dedupe to avoid Postgres ``ON CONFLICT cannot affect row twice``.
"""

from __future__ import annotations

import datetime as _dt
from collections import Counter, defaultdict
from decimal import Decimal
from typing import Callable, Iterable

import pyarrow.parquet as pq
from django.core.cache import cache
from django.db import transaction

from common.logging import get_logger
from ingestion.cleaning import CleanRate, Quarantine, clean_row
from rates.models import Provider, Rate, RawResponse

log = get_logger("loader")

INGESTION_STATUS_KEY = "ingestion:status"


def _idle_status() -> dict:
    return {
        "state": "idle",
        "total": 0,
        "processed": 0,
        "inserted": 0,
        "updated": 0,
        "output": 0,
        "quarantined": 0,
        "started_at": None,
        "finished_at": None,
        "error": None,
    }


def get_ingestion_status() -> dict:
    """Return the current ingestion job status (idle if never run)."""
    return cache.get(INGESTION_STATUS_KEY) or _idle_status()


def set_ingestion_status(status: dict) -> None:
    """Persist the ingestion job status (no TTL — it is a live job marker)."""
    cache.set(INGESTION_STATUS_KEY, status, timeout=None)


def parquet_row_count(path: str) -> int:
    """Total rows in a parquet file via metadata (no full read)."""
    return pq.ParquetFile(path).metadata.num_rows


def _json_safe(value):
    """Recursively convert a raw row into JSON-serializable values.

    Parquet rows carry ``datetime.date``/``datetime`` and ``Decimal`` objects
    that Django's JSONField cannot serialize. Quarantined payloads must remain
    replayable, so we preserve the data as ISO strings rather than dropping it.
    """
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (_dt.date, _dt.datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _rows_from_dict(batch_dict: dict) -> Iterable[dict]:
    """Yield row dicts from a column-oriented batch dict."""
    if not batch_dict:
        return
    keys = list(batch_dict.keys())
    values = list(batch_dict.values())
    for i in range(len(values[0])):
        yield {keys[j]: values[j][i] for j in range(len(keys))}


def stream_seed(
    path: str,
    *,
    batch_size: int = 50_000,
    limit: int | None = None,
    sample: int | None = None,
    dry_run: bool = False,
    progress_cb: Callable[["IngestionResult", int], None] | None = None,
) -> "IngestionResult":
    """Stream a parquet file in batches, clean + upsert each row idempotently.

    Shared by the ``seed_data`` command and the ``seed_full_data`` Celery task.
    ``progress_cb(result, rows_read)`` is invoked after each batch so callers
    can log or publish progress.
    """
    total_result = IngestionResult()
    parquet_file = pq.ParquetFile(path)

    if sample:
        table = parquet_file.read()
        if sample < len(table):
            table = table.slice(0, sample)
        batches: Iterable = [table.to_pydict()]
    else:
        batches = parquet_file.iter_batches(batch_size=batch_size)

    rows_read = 0
    for batch in batches:
        if limit and rows_read >= limit:
            break
        batch_dict = batch if sample else batch.to_pydict()

        clean_rates: list[CleanRate] = []
        quarantined: list[tuple[Quarantine, dict]] = []
        for row in _rows_from_dict(batch_dict):
            if limit and rows_read >= limit:
                break
            rows_read += 1
            result = clean_row(row)
            if isinstance(result, CleanRate):
                clean_rates.append(result)
            else:
                quarantined.append((result, row))

        if clean_rates or quarantined:
            batch_result = ingest_records(clean_rates, quarantined, dry_run=dry_run)
            total_result.read += batch_result.read
            total_result.inserted += batch_result.inserted
            total_result.updated += batch_result.updated
            total_result.providers_created += batch_result.providers_created
            total_result.quarantined.update(batch_result.quarantined)

        if progress_cb is not None:
            progress_cb(total_result, rows_read)

    return total_result


class IngestionResult:
    """Counts and metrics from an ingestion job."""

    def __init__(self) -> None:
        self.read = 0
        self.inserted = 0
        self.updated = 0
        self.quarantined: Counter[str] = Counter()
        self.providers_created = 0

    def to_dict(self) -> dict:
        return {
            "read": self.read,
            "inserted": self.inserted,
            "updated": self.updated,
            "quarantined": dict(self.quarantined),
            "providers_created": self.providers_created,
        }


def ingest_records(
    clean_rates: Iterable[CleanRate],
    quarantined: Iterable[tuple[Quarantine, dict]],
    *,
    dry_run: bool = False,
) -> IngestionResult:
    """Upsert cleaned rates and quarantined raw responses.

    Args:
        clean_rates: Validated, canonicalized rate records.
        quarantined: (Quarantine, raw dict) pairs for failed rows.
        dry_run: If True, log what would happen but don't write to DB.

    Returns:
        IngestionResult with counts.
    """
    result = IngestionResult()
    clean_list = list(clean_rates)
    quarantined_list = list(quarantined)
    result.read = len(clean_list) + len(quarantined_list)

    if dry_run:
        log.info(
            "loader.dry_run",
            extra={
                "would_insert": len(clean_list),
                "would_quarantine": len(quarantined_list),
            },
        )
        return result

    # Resolve providers via canonical slug cache (no per-row DB lookup).
    provider_map, created_providers = _resolve_providers(clean_list)
    result.providers_created = created_providers

    # Upsert RawResponse rows (both parsed and failed).
    _upsert_raw_responses(clean_list, quarantined_list)

    # In-batch dedupe by natural key (latest ingestion_ts wins).
    deduped_rates = _dedupe_by_natural_key(clean_list, provider_map)

    # Upsert Rate rows with natural-key conflict resolution.
    _upsert_rates(deduped_rates, result)

    # Count quarantined reasons.
    for quarantine, _ in quarantined_list:
        result.quarantined[quarantine.reason] += 1

    return result


def _resolve_providers(clean_rates: list[CleanRate]) -> tuple[dict[str, Provider], int]:
    """Resolve provider slugs to Provider objects, creating missing ones.

    Returns a tuple of (slug → Provider map, count of newly created providers).
    """
    slugs = {r.provider_slug for r in clean_rates}
    if not slugs:
        return {}, 0
    existing = {p.slug: p for p in Provider.objects.filter(slug__in=slugs)}
    to_create = []
    for slug in slugs - set(existing.keys()):
        # Find the corresponding CleanRate to get the display name.
        name = next(
            (r.provider_name for r in clean_rates if r.provider_slug == slug),
            slug.replace("-", " ").title(),
        )
        to_create.append(Provider(slug=slug, name=name))
    created_count = len(to_create)
    if to_create:
        Provider.objects.bulk_create(to_create, ignore_conflicts=True)
        # bulk_create(ignore_conflicts=True) does not reliably populate primary
        # keys on the returned objects, so re-query to guarantee every Provider
        # has a PK before it is attached to a Rate (else bulk_create on Rate
        # raises "unsaved related object 'provider'").
        existing = {p.slug: p for p in Provider.objects.filter(slug__in=slugs)}
    return existing, created_count


def _upsert_raw_responses(
    clean_rates: list[CleanRate], quarantined: list[tuple[Quarantine, dict]]
) -> None:
    """Upsert RawResponse rows for both parsed and failed rows."""
    raw_responses = []
    for r in clean_rates:
        raw_responses.append(
            RawResponse(
                external_id=r.raw_response_id,
                source_url=r.source_url,
                payload={"cleaned": True},  # Minimal payload for clean rows.
                status=RawResponse.Status.PARSED,
            )
        )
    for quarantine, raw in quarantined:
        raw_responses.append(
            RawResponse(
                external_id=raw.get("raw_response_id"),
                source_url=raw.get("source_url", ""),
                payload=_json_safe(raw),  # Original pre-clean row (JSON-safe).
                status=RawResponse.Status.FAILED,
                parse_error=quarantine.reason,
            )
        )
    # Bulk upsert on external_id (unique/nullable). Conflict resolution: update.
    RawResponse.objects.bulk_create(
        raw_responses,
        update_conflicts=True,
        unique_fields=["external_id"],
        update_fields=["payload", "status", "parse_error", "source_url"],
        batch_size=10_000,
    )


def _dedupe_by_natural_key(
    clean_rates: list[CleanRate], provider_map: dict[str, Provider]
) -> list[tuple[CleanRate, Provider]]:
    """Dedupe clean rates by natural key (provider, rate_type, effective_date).

    Within a batch, keep the row with the latest ingestion_ts. This avoids
    Postgres ``ON CONFLICT cannot affect row twice`` errors when the same
    key appears multiple times in a single batch.
    """
    key_to_rate: dict[tuple[int, str, _dt.date], CleanRate] = {}
    for r in clean_rates:
        provider_id = provider_map[r.provider_slug].id
        key = (provider_id, r.rate_type, r.effective_date)
        existing = key_to_rate.get(key)
        if existing is None or r.ingestion_ts > existing.ingestion_ts:
            key_to_rate[key] = r
    return [(r, provider_map[r.provider_slug]) for r in key_to_rate.values()]


def _upsert_rates(
    deduped_rates: list[tuple[CleanRate, Provider]], result: IngestionResult
) -> None:
    """Upsert Rate rows with natural-key conflict resolution."""
    rate_objs = []
    for r, provider in deduped_rates:
        rate_objs.append(
            Rate(
                provider=provider,
                rate_type=r.rate_type,
                rate_value=Decimal(str(r.rate_value)),
                currency=r.currency,
                effective_date=r.effective_date,
                ingestion_ts=r.ingestion_ts,
                source_url=r.source_url,
            )
        )
    if not rate_objs:
        return

    # bulk_create(update_conflicts=True) does not report which rows were inserted
    # vs updated, so we derive it from the table-size delta: new rows are true
    # inserts, the remaining affected rows were updates (latest-wins corrections).
    before = Rate.objects.count()
    # Bulk upsert on natural key. Conflict resolution: update.
    # Django 5.1+ supports update_conflicts with update_fields.
    Rate.objects.bulk_create(
        rate_objs,
        update_conflicts=True,
        unique_fields=["provider", "rate_type", "effective_date"],
        update_fields=["rate_value", "currency", "ingestion_ts", "source_url"],
        batch_size=10_000,
    )
    after = Rate.objects.count()
    result.inserted = after - before
    result.updated = len(rate_objs) - result.inserted
