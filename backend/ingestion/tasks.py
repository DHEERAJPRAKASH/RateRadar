"""Celery tasks for rate ingestion.

The ``scrape_rates`` task iterates configured sources, fetches via HTTP,
parses, and upserts via the shared loader. Idempotent and observable.
"""
from __future__ import annotations

from celery import shared_task
from django.utils import timezone

from common.logging import get_logger
from ingestion.cleaning import CleanRate
from ingestion.fetchers import FetchError, FetchHTTPError, FetchTimeout, HttpRateFetcher
from ingestion.loader import (
    get_ingestion_status,
    ingest_records,
    parquet_row_count,
    set_ingestion_status,
    stream_seed,
)
from ingestion.parsers import ParseError, parse_rate_payload
from rates.models import RawResponse

log = get_logger("scrape")
seed_log = get_logger("seed")


@shared_task(bind=True, ignore_result=True)
def seed_full_data(self, path: str = "rates_seed.parquet", batch_size: int = 50_000) -> None:
    """Stream the full parquet seed into the DB, publishing live progress.

    Idempotent and guarded: if rates already exist, the task marks the job
    complete and returns, so re-running ``docker compose up`` stays fast.
    Progress is written to the ``ingestion:status`` cache key after each batch
    so the dashboard can render a progress bar.
    """
    from rates.models import Rate

    if Rate.objects.exists():
        seed_log.info("seed.skip_already_seeded")
        status = get_ingestion_status()
        if status.get("state") != "complete":
            status.update(state="complete", finished_at=timezone.now().isoformat())
            set_ingestion_status(status)
        return

    try:
        total = parquet_row_count(path)
    except Exception as exc:  # noqa: BLE001 - file/metadata problems are surfaced via status
        seed_log.error("seed.metadata_error", exc_info=exc, extra={"path": path})
        set_ingestion_status(
            {
                "state": "error",
                "total": 0,
                "processed": 0,
                "inserted": 0,
                "updated": 0,
                "output": 0,
                "quarantined": 0,
                "started_at": timezone.now().isoformat(),
                "finished_at": timezone.now().isoformat(),
                "error": str(exc),
            }
        )
        return

    started = timezone.now().isoformat()
    set_ingestion_status(
        {
            "state": "running",
            "total": total,
            "processed": 0,
            "inserted": 0,
            "updated": 0,
            "output": 0,
            "quarantined": 0,
            "started_at": started,
            "finished_at": None,
            "error": None,
        }
    )
    seed_log.info("seed.start", extra={"path": path, "total": total})

    def _publish(result, rows_read: int) -> None:
        set_ingestion_status(
            {
                "state": "running",
                "total": total,
                "processed": rows_read,
                # inserted = new rows, updated = re-ingested corrections,
                # output = distinct rows now in the table (inserted + updated
                # collapse to this via the natural-key constraint).
                "inserted": result.inserted,
                "updated": result.updated,
                "output": result.inserted,
                "quarantined": sum(result.quarantined.values()),
                "started_at": started,
                "finished_at": None,
                "error": None,
            }
        )

    try:
        result = stream_seed(path, batch_size=batch_size, progress_cb=_publish)
    except Exception as exc:  # noqa: BLE001
        seed_log.error("seed.error", exc_info=exc)
        set_ingestion_status(
            {
                "state": "error",
                "total": total,
                "processed": 0,
                "inserted": 0,
                "updated": 0,
                "output": 0,
                "quarantined": 0,
                "started_at": started,
                "finished_at": timezone.now().isoformat(),
                "error": str(exc),
            }
        )
        raise

    summary = result.to_dict()
    set_ingestion_status(
        {
            "state": "complete",
            "total": total,
            "processed": summary["read"],
            "inserted": summary["inserted"],
            "updated": summary["updated"],
            "output": summary["inserted"],
            "quarantined": sum(result.quarantined.values()),
            "started_at": started,
            "finished_at": timezone.now().isoformat(),
            "error": None,
        }
    )
    seed_log.info("seed.end", extra=summary)


# In a real system, these would be configured via env or DB.
_SCRAPING_SOURCES = [
    "https://example.com/rates/savings",
    "https://example.com/rates/mortgages",
]


@shared_task(bind=True, ignore_result=True)
def scrape_rates(self) -> None:
    """Fetch, parse, and upsert rates from configured sources.

    Idempotent: re-running the task is a no-op if data hasn't changed.
    Observable: logs per-source counts and errors.
    """
    log.info("scrape.start", extra={"sources": len(_SCRAPING_SOURCES)})
    fetcher = HttpRateFetcher()
    total_read = 0
    total_inserted = 0
    total_quarantined = 0

    for url in _SCRAPING_SOURCES:
        try:
            result = fetcher.fetch(url)
            raw_payload = result["body"]
            try:
                rows = parse_rate_payload(raw_payload)
            except ParseError as exc:
                log.error("scrape.parse_error", extra={"url": url, "error": str(exc)})
                # Store the failed raw response for replay.
                RawResponse.objects.create(
                    source_url=url,
                    payload={"raw": raw_payload},
                    status=RawResponse.Status.FAILED,
                    parse_error=str(exc),
                )
                continue

            # Clean and ingest.
            from ingestion.cleaning import clean_row

            clean_rates = []
            quarantined = []
            for row in rows:
                cleaned = clean_row(row)
                if isinstance(cleaned, CleanRate):
                    clean_rates.append(cleaned)
                else:
                    quarantined.append((cleaned, row))

            result_counts = ingest_records(clean_rates, quarantined)
            total_read += result_counts.read
            total_inserted += result_counts.inserted
            total_quarantined += sum(result_counts.quarantined.values())

            log.info(
                "scrape.source_complete",
                extra={
                    "url": url,
                    "read": result_counts.read,
                    "inserted": result_counts.inserted,
                    "quarantined": dict(result_counts.quarantined),
                },
            )

        except FetchTimeout as exc:
            log.error("scrape.timeout", extra={"url": url, "error": str(exc)})
        except FetchHTTPError as exc:
            log.error("scrape.http_error", extra={"url": url, "status_code": exc.status_code})
        except FetchError as exc:
            log.error("scrape.fetch_error", extra={"url": url, "error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            log.error("scrape.unexpected_error", exc_info=exc, extra={"url": url})

    log.info(
        "scrape.end",
        extra={
            "total_read": total_read,
            "total_inserted": total_inserted,
            "total_quarantined": total_quarantined,
        },
    )
