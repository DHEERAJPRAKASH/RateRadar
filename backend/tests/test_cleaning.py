"""Unit tests for the data cleaning pipeline."""
import datetime as _dt
from decimal import Decimal

import pytest
from django.utils import timezone

from ingestion.cleaning import CleanRate, Quarantine, clean_row


def test_clean_row_valid():
    """A valid row passes through with canonicalization."""
    raw = {
        "provider": "hsbc",
        "rate_type": "savings_1yr_fixed",
        "rate_value": 4.5,
        "currency": "usd",
        "effective_date": "2024-01-15",
        "ingestion_ts": "2024-01-15T10:00:00",
        "source_url": "https://example.com",
        "raw_response_id": "abc123",
    }
    result = clean_row(raw)
    assert isinstance(result, CleanRate)
    assert result.provider_slug == "hsbc"
    assert result.provider_name == "HSBC"  # alias map
    assert result.currency == "USD"  # normalized
    assert result.rate_value == Decimal("4.5")
    assert timezone.is_aware(result.ingestion_ts)


def test_clean_row_provider_canonicalization():
    """Provider casing/dupes collapse to one slug."""
    variants = ["hsbc", "Hsbc", "HSBC", "hSbC"]
    for variant in variants:
        raw = {
            "provider": variant,
            "rate_type": "savings_1yr_fixed",
            "rate_value": 4.5,
            "currency": "USD",
            "effective_date": "2024-01-15",
            "ingestion_ts": "2024-01-15T10:00:00",
        }
        result = clean_row(raw)
        assert isinstance(result, CleanRate)
        assert result.provider_slug == "hsbc"
        assert result.provider_name == "HSBC"


def test_clean_row_unknown_provider_fallback():
    """Unknown providers fall back to title-cased slug."""
    raw = {
        "provider": "unknown bank",
        "rate_type": "savings_1yr_fixed",
        "rate_value": 4.5,
        "currency": "USD",
        "effective_date": "2024-01-15",
        "ingestion_ts": "2024-01-15T10:00:00",
    }
    result = clean_row(raw)
    assert isinstance(result, CleanRate)
    assert result.provider_slug == "unknown-bank"
    assert result.provider_name == "Unknown Bank"


def test_clean_row_currency_normalization():
    """Currency variants normalize to ISO codes."""
    variants = ["USD", "usd", "US Dollar", "usd "]
    for variant in variants:
        raw = {
            "provider": "hsbc",
            "rate_type": "savings_1yr_fixed",
            "rate_value": 4.5,
            "currency": variant,
            "effective_date": "2024-01-15",
            "ingestion_ts": "2024-01-15T10:00:00",
        }
        result = clean_row(raw)
        assert isinstance(result, CleanRate)
        assert result.currency == "USD"


def test_clean_row_unknown_currency_quarantine():
    """Unknown currencies are quarantined."""
    raw = {
        "provider": "hsbc",
        "rate_type": "savings_1yr_fixed",
        "rate_value": 4.5,
        "currency": "XYZ",
        "effective_date": "2024-01-15",
        "ingestion_ts": "2024-01-15T10:00:00",
    }
    result = clean_row(raw)
    assert isinstance(result, Quarantine)
    assert "unknown currency" in result.reason


def test_clean_row_null_rate_value_quarantine():
    """Null rate_value is quarantined (the EDA case)."""
    raw = {
        "provider": "hsbc",
        "rate_type": "savings_1yr_fixed",
        "rate_value": None,
        "currency": "USD",
        "effective_date": "2024-01-15",
        "ingestion_ts": "2024-01-15T10:00:00",
    }
    result = clean_row(raw)
    assert isinstance(result, Quarantine)
    assert result.reason == "null rate_value"


def test_clean_row_negative_rate_value_quarantine():
    """Negative rates are quarantined."""
    raw = {
        "provider": "hsbc",
        "rate_type": "savings_1yr_fixed",
        "rate_value": -1.5,
        "currency": "USD",
        "effective_date": "2024-01-15",
        "ingestion_ts": "2024-01-15T10:00:00",
    }
    result = clean_row(raw)
    assert isinstance(result, Quarantine)
    assert "negative rate_value" in result.reason


def test_clean_row_out_of_range_rate_value_quarantine():
    """Rates >100% are quarantined (sane range)."""
    raw = {
        "provider": "hsbc",
        "rate_type": "savings_1yr_fixed",
        "rate_value": 150.0,
        "currency": "USD",
        "effective_date": "2024-01-15",
        "ingestion_ts": "2024-01-15T10:00:00",
    }
    result = clean_row(raw)
    assert isinstance(result, Quarantine)
    assert "out of sane range" in result.reason


def test_clean_row_blank_provider_quarantine():
    """Blank provider is quarantined."""
    raw = {
        "provider": "",
        "rate_type": "savings_1yr_fixed",
        "rate_value": 4.5,
        "currency": "USD",
        "effective_date": "2024-01-15",
        "ingestion_ts": "2024-01-15T10:00:00",
    }
    result = clean_row(raw)
    assert isinstance(result, Quarantine)
    assert "provider" in result.reason


def test_clean_row_blank_rate_type_quarantine():
    """Blank rate_type is quarantined."""
    raw = {
        "provider": "hsbc",
        "rate_type": "",
        "rate_value": 4.5,
        "currency": "USD",
        "effective_date": "2024-01-15",
        "ingestion_ts": "2024-01-15T10:00:00",
    }
    result = clean_row(raw)
    assert isinstance(result, Quarantine)
    assert "rate_type" in result.reason


def test_clean_row_missing_effective_date_quarantine():
    """Missing effective_date is quarantined."""
    raw = {
        "provider": "hsbc",
        "rate_type": "savings_1yr_fixed",
        "rate_value": 4.5,
        "currency": "USD",
        "ingestion_ts": "2024-01-15T10:00:00",
    }
    result = clean_row(raw)
    assert isinstance(result, Quarantine)
    assert "effective_date" in result.reason


def test_clean_row_future_effective_date_quarantine():
    """Dates far in the future (>30 days) are quarantined."""
    future = _dt.date.today() + _dt.timedelta(days=60)
    raw = {
        "provider": "hsbc",
        "rate_type": "savings_1yr_fixed",
        "rate_value": 4.5,
        "currency": "USD",
        "effective_date": future.isoformat(),
        "ingestion_ts": "2024-01-15T10:00:00",
    }
    result = clean_row(raw)
    assert isinstance(result, Quarantine)
    assert "too far in future" in result.reason


def test_clean_row_missing_ingestion_ts_quarantine():
    """Missing ingestion_ts is quarantined."""
    raw = {
        "provider": "hsbc",
        "rate_type": "savings_1yr_fixed",
        "rate_value": 4.5,
        "currency": "USD",
        "effective_date": "2024-01-15",
    }
    result = clean_row(raw)
    assert isinstance(result, Quarantine)
    assert "ingestion_ts" in result.reason


def test_clean_row_date_objects():
    """Accepts native date/datetime objects (not just strings)."""
    raw = {
        "provider": "hsbc",
        "rate_type": "savings_1yr_fixed",
        "rate_value": 4.5,
        "currency": "USD",
        "effective_date": _dt.date(2024, 1, 15),
        "ingestion_ts": _dt.datetime(2024, 1, 15, 10, 0, 0),
    }
    result = clean_row(raw)
    assert isinstance(result, CleanRate)
    assert result.effective_date == _dt.date(2024, 1, 15)
    assert result.ingestion_ts == _dt.datetime(
        2024, 1, 15, 10, 0, 0, tzinfo=_dt.timezone.utc
    )
