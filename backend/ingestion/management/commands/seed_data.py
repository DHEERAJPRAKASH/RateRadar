"""Django management command to load rates from a Snappy parquet file.

Streams the file in batches, validates/canonicalizes each row, and upserts
idempotently. Supports ``--sample N`` for fast boot-time seeding.
"""

from __future__ import annotations

import argparse
import pathlib

from django.core.management.base import BaseCommand

from common.logging import get_logger

# Re-exported for backwards compatibility (tests import it from here).
from ingestion.services.loader import _rows_from_dict, stream_seed  # noqa: F401

log = get_logger("seed")


class Command(BaseCommand):
    help = "Load rate data from a Snappy parquet file (idempotent)."

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--path",
            type=str,
            default="rates_seed.parquet",
            help="Path to the parquet file (default: rates_seed.parquet).",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=50_000,
            help="Batch size for reading (default: 50_000).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Limit total rows read (for testing).",
        )
        parser.add_argument(
            "--sample",
            type=int,
            default=None,
            help="Sample N rows randomly (for fast boot-time seeding).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Log what would happen without writing to DB.",
        )
        parser.add_argument(
            "--async",
            dest="run_async",
            action="store_true",
            help="Enqueue the full seed as a Celery task instead of running inline.",
        )

    def handle(self, *args, **options: dict) -> None:
        path = options["path"]
        batch_size = options["batch_size"]
        limit = options["limit"]
        sample = options["sample"]
        dry_run = options["dry_run"]
        run_async = options["run_async"]

        if run_async:
            # Defer to the worker; entrypoint uses this for non-blocking boot seed.
            from ingestion.services.tasks import seed_full_data

            seed_full_data.delay(path=path, batch_size=batch_size)
            log.info("seed.enqueued", extra={"path": path})
            self.stdout.write(self.style.SUCCESS("Seed task enqueued."))
            return

        log.info(
            "seed.start",
            extra={
                "path": path,
                "batch_size": batch_size,
                "limit": limit,
                "sample": sample,
                "dry_run": dry_run,
            },
        )

        if not pathlib.Path(path).exists():
            log.error("seed.file_not_found", extra={"path": path})
            self.stderr.write(self.style.ERROR(f"File not found: {path}"))
            return

        try:
            total_result = stream_seed(
                path,
                batch_size=batch_size,
                limit=limit,
                sample=sample,
                dry_run=dry_run,
            )
        except Exception as exc:
            log.error("seed.error", exc_info=exc)
            self.stderr.write(self.style.ERROR(f"Error: {exc}"))
            raise

        summary = total_result.to_dict()
        log.info("seed.end", extra=summary)
        self.stdout.write(self.style.SUCCESS(f"Seed complete: {summary}"))
