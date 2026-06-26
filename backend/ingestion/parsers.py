"""Parser for rate payloads.

Parses raw HTTP responses into a list of raw rate dicts. This is
source-agnostic; the actual source-specific parsing logic would go here.
For the assessment, we assume a simple JSON structure.
"""
from __future__ import annotations

import json
from typing import Any

from common.logging import get_logger

log = get_logger("parser")


class ParseError(Exception):
    """Base class for parse errors."""


def parse_rate_payload(body: str) -> list[dict[str, Any]]:
    """Parse a rate payload into a list of raw rate dicts.

    The expected structure is a JSON array of objects with the same schema
    as the parquet file. For the assessment, we assume a simple format.

    Args:
        body: Raw response body (JSON string).

    Returns:
        List of raw rate dicts.

    Raises:
        ParseError: if the body is not valid JSON or does not match the expected structure.
    """
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ParseError(f"Invalid JSON: {exc}") from exc

    if not isinstance(data, list):
        raise ParseError(f"Expected JSON array, got {type(data).__name__}")

    # Validate that each item is a dict with required keys.
    required_keys = {"provider", "rate_type", "rate_value", "effective_date", "ingestion_ts"}
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise ParseError(f"Item {i} is not a dict: {type(item).__name__}")
        missing = required_keys - set(item.keys())
        if missing:
            raise ParseError(f"Item {i} missing keys: {missing}")

    return data
