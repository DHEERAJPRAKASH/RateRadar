"""Structured JSON logging.

A single ``JsonFormatter`` is used by every handler so that container logs are
machine-parseable. Use ``get_logger(__name__)`` and pass structured context via
the ``extra`` kwarg, e.g.::

    log.info("seed.start", extra={"path": path, "batch_size": 50_000})
"""
from __future__ import annotations

import datetime as _dt
import logging

from pythonjsonlogger import jsonlogger

LOGGER_NAMESPACE = "rateradar"


class JsonFormatter(jsonlogger.JsonFormatter):
    """Adds ISO-8601 UTC timestamp and a normalised ``level`` field."""

    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        log_record["timestamp"] = _dt.datetime.fromtimestamp(
            record.created, tz=_dt.timezone.utc
        ).isoformat()
        log_record["level"] = record.levelname
        log_record["logger"] = record.name
        if record.exc_info and "exc_info" not in log_record:
            log_record["exc_info"] = self.formatException(record.exc_info)


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a logger under the ``rateradar`` namespace."""
    suffix = name.split(".")[-1] if name else "app"
    return logging.getLogger(f"{LOGGER_NAMESPACE}.{suffix}")
