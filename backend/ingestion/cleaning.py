"""Data cleaning and validation pipeline.

A single ``clean_row(raw) -> CleanRate | Quarantine`` function shared by
``seed_data``, the scraper, and ``POST /rates/ingest``. It:

- Canonicalizes provider names via slug (collapses ``hsbc``/``Hsbc``/``HSBC`` → ``hsbc``).
- Normalizes currency to ISO codes (``USD``/``usd``/``US Dollar`` → ``USD``).
- Validates every row defensively; invalid rows are quarantined with a reason,
  never crash the worker.

The original raw row is preserved in ``RawResponse.payload`` so quarantined
records can be replayed after a fix.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal

from django.utils import timezone
from django.utils.text import slugify

# Curated alias map for provider display names (canonical slug → display name).
# Unknown providers fall back to title-cased slug.
_PROVIDER_ALIAS_MAP: dict[str, str] = {
    "hsbc": "HSBC",
    "bank-of-america": "Bank of America",
    "chase": "Chase",
    "wells-fargo": "Wells Fargo",
    "citibank": "Citibank",
    "capital-one": "Capital One",
    "pnc-bank": "PNC Bank",
    "td-bank": "TD Bank",
    "us-bancorp": "US Bancorp",
    "truist": "Truist",
}

# Currency normalization map (lowercase stripped → ISO code).
_CURRENCY_MAP: dict[str, str] = {
    "usd": "USD",
    "us dollar": "USD",
    "usd ": "USD",
    "eur": "EUR",
    "euro": "EUR",
    "gbp": "GBP",
    "pound": "GBP",
}


@dataclass(frozen=True)
class CleanRate:
    """A validated, canonicalized rate record ready for DB insertion."""

    provider_slug: str
    provider_name: str
    rate_type: str
    rate_value: Decimal
    currency: str
    effective_date: _dt.date
    ingestion_ts: _dt.datetime
    source_url: str
    raw_response_id: str | None


@dataclass(frozen=True)
class Quarantine:
    """A row that failed validation with a human-readable reason."""

    reason: str


def clean_row(raw: dict) -> CleanRate | Quarantine:
    """Validate and canonicalize a raw rate row.

    Returns ``CleanRate`` if the row passes all checks, otherwise ``Quarantine``
    with a reason. The original ``raw`` dict is preserved in ``RawResponse.payload``.
    """
    # Provider canonicalization: slug is the dedup key.
    provider_raw = _get_str(raw, "provider")
    if not provider_raw:
        return Quarantine("missing or blank provider")
    provider_slug = slugify(provider_raw.strip().lower())
    provider_name = _PROVIDER_ALIAS_MAP.get(
        provider_slug, provider_slug.replace("-", " ").title()
    )

    # Currency normalization.
    currency_raw = _get_str(raw, "currency", default="USD")
    if not currency_raw:
        return Quarantine("missing or blank currency")
    currency_key = currency_raw.strip().lower()
    currency = _CURRENCY_MAP.get(currency_key)
    if currency is None:
        return Quarantine(f"unknown currency: {currency_raw}")

    # Rate value validation.
    rate_value_raw = raw.get("rate_value")
    if rate_value_raw is None:
        return Quarantine("null rate_value")
    try:
        rate_value = Decimal(str(rate_value_raw))
    except (InvalidOperation, ValueError, TypeError):
        return Quarantine(f"non-numeric rate_value: {rate_value_raw}")
    if rate_value < 0:
        return Quarantine(f"negative rate_value: {rate_value}")
    if rate_value > 100:
        return Quarantine(f"rate_value out of sane range (>100%): {rate_value}")

    # Rate type validation (warned but kept if unknown).
    rate_type = _get_str(raw, "rate_type")
    if not rate_type:
        return Quarantine("missing or blank rate_type")

    # Effective date validation.
    effective_date_raw = raw.get("effective_date")
    if effective_date_raw is None:
        return Quarantine("missing effective_date")
    try:
        if isinstance(effective_date_raw, _dt.date):
            effective_date = effective_date_raw
        else:
            effective_date = _dt.date.fromisoformat(str(effective_date_raw))
    except (ValueError, TypeError):
        return Quarantine(f"unparseable effective_date: {effective_date_raw}")
    # Reject dates far in the future (tolerance: 30 days).
    if effective_date > (_dt.date.today() + _dt.timedelta(days=30)):
        return Quarantine(f"effective_date too far in future: {effective_date}")

    # Ingestion timestamp validation.
    ingestion_ts_raw = raw.get("ingestion_ts")
    if ingestion_ts_raw is None:
        return Quarantine("missing ingestion_ts")
    try:
        if isinstance(ingestion_ts_raw, _dt.datetime):
            ingestion_ts = ingestion_ts_raw
        else:
            ingestion_ts = _dt.datetime.fromisoformat(str(ingestion_ts_raw))
    except (ValueError, TypeError):
        return Quarantine(f"unparseable ingestion_ts: {ingestion_ts_raw}")
    if timezone.is_naive(ingestion_ts):
        ingestion_ts = timezone.make_aware(ingestion_ts, _dt.timezone.utc)

    source_url = _get_str(raw, "source_url", default="")
    raw_response_id = _get_str(raw, "raw_response_id")

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


def _get_str(raw: dict, key: str, default: str = "") -> str:
    """Extract a string value from a dict, defaulting to empty string."""
    val = raw.get(key)
    if val is None:
        return default
    return str(val).strip()
