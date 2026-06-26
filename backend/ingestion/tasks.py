"""Celery tasks for rate ingestion.

The ``scrape_rates`` task iterates configured sources, fetches via HTTP,
parses, and upserts via the shared loader. Idempotent and observable.
"""
from __future__ import annotations

from celery import shared_task

from common.logging import get_logger
from ingestion.fetchers import FetchError, FetchHTTPError, FetchTimeout, HttpRateFetcher
from ingestion.loader import ingest_records
from ingestion.parsers import ParseError, parse_rate_payload
from rates.models import RawResponse

log = get_logger("scrape")


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
                if isinstance(cleaned, tuple):
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
