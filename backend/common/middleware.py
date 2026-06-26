"""Request-scoped observability.

For each request we:
- install a DB ``execute_wrapper`` that logs a WARNING for any single query
  slower than ``settings.SLOW_QUERY_MS``;
- log a structured line per request with method, path, status and duration.
"""
from __future__ import annotations

import time

from django.conf import settings
from django.db import connection

from common.logging import get_logger

log = get_logger("http")


class _SlowQueryWrapper:
    """django DB ``execute_wrapper`` that times each query."""

    def __init__(self, threshold_ms: int):
        self.threshold_ms = threshold_ms

    def __call__(self, execute, sql, params, many, context):
        start = time.perf_counter()
        try:
            return execute(sql, params, many, context)
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            if elapsed_ms >= self.threshold_ms:
                log.warning(
                    "db.slow_query",
                    extra={
                        "duration_ms": round(elapsed_ms, 2),
                        "threshold_ms": self.threshold_ms,
                        "sql": (sql[:500] if isinstance(sql, str) else str(sql)),
                    },
                )


class RequestTimingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.threshold_ms = getattr(settings, "SLOW_QUERY_MS", 200)

    def __call__(self, request):
        start = time.perf_counter()
        with connection.execute_wrapper(_SlowQueryWrapper(self.threshold_ms)):
            response = self.get_response(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        log.info(
            "http.request",
            extra={
                "method": request.method,
                "path": request.path,
                "status": response.status_code,
                "duration_ms": round(elapsed_ms, 2),
            },
        )
        if elapsed_ms >= self.threshold_ms:
            log.warning(
                "http.slow_request",
                extra={
                    "method": request.method,
                    "path": request.path,
                    "duration_ms": round(elapsed_ms, 2),
                    "threshold_ms": self.threshold_ms,
                },
            )
        return response
