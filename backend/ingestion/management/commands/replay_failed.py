"""Django management command to re-parse failed raw responses.

Iterates over RawResponse rows with status=FAILED, re-runs the cleaning
pipeline, and upserts any newly valid rows. Useful after fixing a bug in
the cleaning logic.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from common.logging import get_logger
from ingestion.cleaning import clean_row
from ingestion.loader import ingest_records
from rates.models import RawResponse

log = get_logger("replay")


class Command(BaseCommand):
    help = "Re-parse failed raw responses and upsert valid rows."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Limit number of failed rows to replay.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Log what would happen without writing to DB.",
        )

    def handle(self, *args, **options) -> None:
        limit = options["limit"]
        dry_run = options["dry_run"]

        log.info("replay.start", extra={"limit": limit, "dry_run": dry_run})

        queryset = RawResponse.objects.filter(status=RawResponse.Status.FAILED).order_by("created_at")
        if limit:
            queryset = queryset[:limit]

        total_read = 0
        total_inserted = 0
        total_quarantined = 0

        for raw in queryset:
            total_read += 1
            payload = raw.payload
            if not isinstance(payload, dict):
                log.warning("replay.invalid_payload", extra={"id": raw.id})
                continue

            cleaned = clean_row(payload)
            if isinstance(cleaned, tuple):
                clean_rates = [cleaned]
                quarantined = []
            else:
                clean_rates = []
                quarantined = [(cleaned, payload)]

            result = ingest_records(clean_rates, quarantined, dry_run=dry_run)
            total_inserted += result.inserted
            total_quarantined += sum(result.quarantined.values())

            # Update the RawResponse status if we successfully parsed it.
            if not dry_run and clean_rates:
                raw.status = RawResponse.Status.PARSED
                raw.parse_error = None
                raw.save(update_fields=["status", "parse_error"])

        log.info(
            "replay.end",
            extra={
                "read": total_read,
                "inserted": total_inserted,
                "quarantined": total_quarantined,
            },
        )
        self.stdout.write(self.style.SUCCESS(f"Replay complete: read={total_read}, inserted={total_inserted}, quarantined={total_quarantined}"))
