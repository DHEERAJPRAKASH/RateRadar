"""Django management command to load rates from a Snappy parquet file.

Streams the file in batches, validates/canonicalizes each row, and upserts
idempotently. Supports ``--sample N`` for fast boot-time seeding.
"""

from __future__ import annotations

import argparse
import pathlib
from typing import Iterable

import pyarrow.parquet as pq

from django.core.management.base import BaseCommand

from common.logging import get_logger
from ingestion.cleaning import CleanRate, Quarantine, clean_row
from ingestion.loader import ingest_records

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

    def handle(self, *args, **options: dict) -> None:
        path = options["path"]
        batch_size = options["batch_size"]
        limit = options["limit"]
        sample = options["sample"]
        dry_run = options["dry_run"]

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

        total_read = 0
        total_result = ingest_records(
            [], [], dry_run=dry_run
        )  # Initialize with empty result

        try:
            parquet_file = pq.ParquetFile(path)
            if sample:
                # Sample N rows randomly by reading the whole file (fast for 1M rows).
                table = parquet_file.read()
                if sample < len(table):
                    table = table.slice(0, sample)
                batches = [table.to_pydict()]
            else:
                # Stream in batches.
                batches = parquet_file.iter_batches(batch_size=batch_size)

            for batch in batches:
                if limit and total_read >= limit:
                    break

                if sample:
                    # batch is already a dict from table.to_pydict()
                    rows = _rows_from_dict(batch)
                else:
                    # Convert pyarrow batch to dict, then to rows.
                    rows = _rows_from_dict(batch.to_pydict())

                clean_rates: list[CleanRate] = []
                quarantined: list[tuple[Quarantine, dict]] = []

                for row in rows:
                    if limit and total_read >= limit:
                        break
                    total_read += 1

                    result = clean_row(row)
                    if isinstance(result, CleanRate):
                        clean_rates.append(result)
                    else:
                        quarantined.append((result, row))

                if clean_rates or quarantined:
                    batch_result = ingest_records(
                        clean_rates, quarantined, dry_run=dry_run
                    )
                    total_result.read += batch_result.read
                    total_result.inserted += batch_result.inserted
                    total_result.updated += batch_result.updated
                    total_result.providers_created += batch_result.providers_created
                    total_result.quarantined.update(batch_result.quarantined)

        except Exception as exc:
            log.error("seed.error", exc_info=exc)
            self.stderr.write(self.style.ERROR(f"Error: {exc}"))
            raise

        summary = total_result.to_dict()
        log.info("seed.end", extra=summary)
        self.stdout.write(self.style.SUCCESS(f"Seed complete: {summary}"))


def _rows_from_dict(batch_dict: dict) -> Iterable[dict]:
    """Yield row dicts from a batch dict (column-oriented to row-oriented)."""
    if not batch_dict:
        return
    keys = list(batch_dict.keys())
    values = list(batch_dict.values())
    for i in range(len(values[0])):
        yield {keys[j]: values[j][i] for j in range(len(keys))}
