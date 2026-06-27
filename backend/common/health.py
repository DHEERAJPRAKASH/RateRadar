"""Liveness/readiness probe used by docker-compose healthchecks."""

from __future__ import annotations

from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.views import View


class HealthView(View):
    """GET /health — database and cache connectivity check."""

    def get(self, request) -> JsonResponse:
        checks = {"database": False, "cache": False}
        status = 200

        try:
            connection.ensure_connection()
            checks["database"] = connection.is_usable()
            if not checks["database"]:
                status = 503
        except Exception:  # noqa: BLE001
            status = 503

        try:
            cache.set("healthcheck", "ok", timeout=5)
            checks["cache"] = cache.get("healthcheck") == "ok"
            if not checks["cache"]:
                status = 503
        except Exception:  # noqa: BLE001
            status = 503

        return JsonResponse(
            {"status": "ok" if status == 200 else "degraded", "checks": checks},
            status=status,
        )
