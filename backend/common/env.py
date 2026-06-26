"""Environment variable access with fail-fast semantics.

A missing *required* variable raises ``ImproperlyConfigured`` at import/startup
time with a clear, actionable message — never a cryptic crash deep into a
request. This is the single choke point for reading configuration.
"""
from __future__ import annotations

import os
from typing import Any, Callable

from django.core.exceptions import ImproperlyConfigured

_SENTINEL = object()
_TRUE_VALUES = {"1", "true", "yes", "on", "y", "t"}


def get_env(
    name: str,
    default: Any = _SENTINEL,
    *,
    cast: Callable[[str], Any] | type | None = None,
) -> Any:
    """Return the env var ``name``.

    - If unset and no ``default`` is supplied, raise ``ImproperlyConfigured``.
    - ``cast=bool`` parses common truthy strings; other callables are applied
      directly and surface a clear error on failure.
    """
    raw = os.environ.get(name, _SENTINEL)
    if raw is _SENTINEL:
        if default is _SENTINEL:
            raise ImproperlyConfigured(
                f"Missing required environment variable: {name}. "
                f"Copy .env.example to .env and set it (see README)."
            )
        return default

    if cast is bool:
        return str(raw).strip().lower() in _TRUE_VALUES
    if cast is not None:
        try:
            return cast(raw)
        except (TypeError, ValueError) as exc:
            raise ImproperlyConfigured(
                f"Invalid value for environment variable {name}={raw!r}: {exc}"
            ) from exc
    return raw


def get_required_env(name: str, *, cast: Callable[[str], Any] | type | None = None) -> Any:
    """Explicit alias for a required variable (no default)."""
    return get_env(name, cast=cast)


def get_csv_env(name: str, default: str = "") -> list[str]:
    """Parse a comma-separated env var into a stripped, non-empty list."""
    raw = get_env(name, default)
    return [item.strip() for item in str(raw).split(",") if item.strip()]
