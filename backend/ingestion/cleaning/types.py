"""Cleaning pipeline data types."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class CleanRate:
    """A validated, canonicalized rate record ready for DB insertion."""

    provider_slug: str
    provider_name: str
    rate_type: str
    rate_value: Decimal
    currency: str
    effective_date: dt.date
    ingestion_ts: dt.datetime
    source_url: str
    raw_response_id: str | None


@dataclass(frozen=True)
class Quarantine:
    """A row that failed validation with a human-readable reason."""

    reason: str
