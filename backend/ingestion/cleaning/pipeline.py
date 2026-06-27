"""Orchestrates per-field validators into a single clean_row entry point."""

from __future__ import annotations

from ingestion.cleaning.types import CleanRate, Quarantine
from ingestion.cleaning.validators import (
    clean_currency,
    clean_effective_date,
    clean_ingestion_ts,
    clean_metadata,
    clean_provider,
    clean_rate_type,
    clean_rate_value,
)


def _first_quarantine(*results) -> Quarantine | None:
    """Return the first Quarantine in a sequence of validator results."""
    return next((r for r in results if isinstance(r, Quarantine)), None)


def clean_row(raw: dict) -> CleanRate | Quarantine:
    """Validate and canonicalize a raw rate row.

    Each field is cleaned by a dedicated validator; the first failure
    quarantines the row. The original ``raw`` dict is preserved in
    ``RawResponse.payload`` for replay.
    """
    provider = clean_provider(raw)
    if isinstance(provider, Quarantine):
        return provider
    provider_slug, provider_name = provider

    currency = clean_currency(raw)
    rate_value = clean_rate_value(raw)
    rate_type = clean_rate_type(raw)
    effective_date = clean_effective_date(raw)
    ingestion_ts = clean_ingestion_ts(raw)

    if err := _first_quarantine(
        currency, rate_value, rate_type, effective_date, ingestion_ts
    ):
        return err

    source_url, raw_response_id = clean_metadata(raw)

    return CleanRate(
        provider_slug=provider_slug,
        provider_name=provider_name,
        rate_type=rate_type,
        rate_value=rate_value,
        currency=currency,
        effective_date=effective_date,
        ingestion_ts=ingestion_ts,
        source_url=source_url,
        raw_response_id=raw_response_id,
    )
