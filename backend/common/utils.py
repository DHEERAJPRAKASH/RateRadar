"""Shared helpers used across apps."""

from __future__ import annotations

import datetime as dt

import pydash


def get_str(raw: dict, key: str, default: str = "") -> str:
    """Extract a stripped string from a dict, defaulting when absent/null."""
    val = pydash.get(raw, key)
    if val is None:
        return default
    return str(val).strip()


def parse_date(value: str | None) -> dt.date | None:
    """Parse an ISO date string, returning None if absent or invalid."""
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value)
    except (ValueError, TypeError):
        return None
