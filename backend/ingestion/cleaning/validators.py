"""One validator per field — each returns a value or a Quarantine reason."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal, InvalidOperation

import pydash
from django.utils import timezone
from django.utils.text import slugify

from common.utils import get_str
from ingestion.cleaning.constants import (
    FUTURE_DATE_TOLERANCE_DAYS,
    _CURRENCY_MAP,
    _PROVIDER_ALIAS_MAP,
)
from ingestion.cleaning.types import Quarantine


def clean_provider(raw: dict) -> tuple[str, str] | Quarantine:
    """Canonicalize provider name → (slug, display name)."""
    provider_raw = get_str(raw, "provider")
    if not provider_raw:
        return Quarantine("missing or blank provider")
    slug = slugify(provider_raw.strip().lower())
    name = pydash.get(_PROVIDER_ALIAS_MAP, slug, slug.replace("-", " ").title())
    return slug, name


def clean_currency(raw: dict) -> str | Quarantine:
    """Normalize currency to a known ISO code."""
    currency_raw = get_str(raw, "currency", default="USD")
    if not currency_raw:
        return Quarantine("missing or blank currency")
    normalized = pydash.get(_CURRENCY_MAP, currency_raw.strip().lower())
    if normalized is None:
        return Quarantine(f"unknown currency: {currency_raw}")
    return normalized


def clean_rate_value(raw: dict) -> Decimal | Quarantine:
    """Validate rate_value is numeric and within sane bounds."""
    rate_value_raw = pydash.get(raw, "rate_value")
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
    return rate_value


def clean_rate_type(raw: dict) -> str | Quarantine:
    """Ensure rate_type is present."""
    rate_type = get_str(raw, "rate_type")
    if not rate_type:
        return Quarantine("missing or blank rate_type")
    return rate_type


def clean_effective_date(raw: dict) -> dt.date | Quarantine:
    """Parse and bounds-check effective_date."""
    effective_date_raw = pydash.get(raw, "effective_date")
    if effective_date_raw is None:
        return Quarantine("missing effective_date")
    try:
        if isinstance(effective_date_raw, dt.date):
            effective_date = effective_date_raw
        else:
            effective_date = dt.date.fromisoformat(str(effective_date_raw))
    except (ValueError, TypeError):
        return Quarantine(f"unparseable effective_date: {effective_date_raw}")
    if effective_date > (dt.date.today() + dt.timedelta(days=FUTURE_DATE_TOLERANCE_DAYS)):
        return Quarantine(f"effective_date too far in future: {effective_date}")
    return effective_date


def clean_ingestion_ts(raw: dict) -> dt.datetime | Quarantine:
    """Parse ingestion_ts and ensure timezone awareness."""
    ingestion_ts_raw = pydash.get(raw, "ingestion_ts")
    if ingestion_ts_raw is None:
        return Quarantine("missing ingestion_ts")
    try:
        if isinstance(ingestion_ts_raw, dt.datetime):
            ingestion_ts = ingestion_ts_raw
        else:
            ingestion_ts = dt.datetime.fromisoformat(str(ingestion_ts_raw))
    except (ValueError, TypeError):
        return Quarantine(f"unparseable ingestion_ts: {ingestion_ts_raw}")
    if timezone.is_naive(ingestion_ts):
        ingestion_ts = timezone.make_aware(ingestion_ts, dt.timezone.utc)
    return ingestion_ts


def clean_metadata(raw: dict) -> tuple[str, str | None]:
    """Extract optional source_url and raw_response_id (always succeeds)."""
    return get_str(raw, "source_url", default=""), get_str(raw, "raw_response_id") or None
