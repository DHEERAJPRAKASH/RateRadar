"""Ingest webhook business logic."""

from __future__ import annotations

import pydash
from django.core.cache import cache

from common.logging import get_logger
from ingestion.cleaning import CleanRate, Quarantine, clean_row
from ingestion.services.loader import ingest_records

log = get_logger("api")


class IngestService:
    """Clean raw rows and upsert via the shared loader."""

    @classmethod
    def ingest_payload(cls, raw_rows: list[dict]) -> dict:
        log.info("api.ingest.start", extra={"count": len(raw_rows)})
        clean_rates, quarantined = cls._partition_rows(raw_rows)
        result = ingest_records(clean_rates, quarantined)
        cache.delete("rates:latest:all")
        log.info("api.ingest.end", extra=result.to_dict())
        return result.to_dict()

    @staticmethod
    def _partition_rows(
        raw_rows: list[dict],
    ) -> tuple[list[CleanRate], list[tuple[Quarantine, dict]]]:
        """Split raw rows into clean rates and quarantined pairs."""
        clean_rates: list[CleanRate] = []
        quarantined: list[tuple[Quarantine, dict]] = []
        for row in raw_rows:
            cleaned = clean_row(row)
            if isinstance(cleaned, CleanRate):
                clean_rates.append(cleaned)
            else:
                quarantined.append((cleaned, row))
        return clean_rates, quarantined
