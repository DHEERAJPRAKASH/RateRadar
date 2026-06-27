"""Rate query and metadata business logic."""

from __future__ import annotations

import datetime as dt

from django.core.cache import cache
from django.db.models import OuterRef, Subquery

from common.logging import get_logger
from common.utils import parse_date
from rates.models import Provider, Rate, RawResponse
from rates.serializers import RateSerializer

log = get_logger("api")

CACHE_TTL_SECONDS = 60


class RateQueryService:
    """Read-side operations for rate data (queries, caching, metadata)."""

    @classmethod
    def _latest_rates_queryset(cls, rate_type: str | None):
        """Latest rate per provider via correlated subquery (no raw SQL)."""
        inner = Rate.objects.filter(provider_id=OuterRef("provider_id"))
        if rate_type:
            inner = inner.filter(rate_type=rate_type)

        latest_pk = inner.order_by("-effective_date", "-ingestion_ts").values("pk")[:1]
        qs = Rate.objects.filter(pk=Subquery(latest_pk))
        if rate_type:
            qs = qs.filter(rate_type=rate_type)
        return qs.select_related("provider")

    @classmethod
    def get_latest_rates(cls, rate_type: str | None) -> tuple[list, bool]:
        """Return (serialized rates, cache_hit)."""
        cache_key = f"rates:latest:{rate_type or 'all'}"
        cached = cache.get(cache_key)
        if cached is not None:
            log.info("api.cache_hit", extra={"endpoint": "latest", "rate_type": rate_type})
            return cached, True

        rates = cls._latest_rates_queryset(rate_type)
        data = RateSerializer(rates, many=True).data
        cache.set(cache_key, data, timeout=CACHE_TTL_SECONDS)
        log.info(
            "api.cache_miss",
            extra={"endpoint": "latest", "rate_type": rate_type, "count": len(data)},
        )
        return data, False

    @classmethod
    def get_history(
        cls,
        provider_slug: str,
        rate_type: str,
        date_from: dt.date,
        date_to: dt.date,
    ) -> tuple[list, bool]:
        """Return (serialized history, cache_hit)."""
        cache_key = f"rates:history:{provider_slug}:{rate_type}:{date_from}:{date_to}"
        cached = cache.get(cache_key)
        if cached is not None:
            log.info(
                "api.cache_hit",
                extra={
                    "endpoint": "history",
                    "provider": provider_slug,
                    "rate_type": rate_type,
                },
            )
            return cached, True

        rates = (
            Rate.objects.filter(
                provider__slug=provider_slug,
                rate_type=rate_type,
                effective_date__gte=date_from,
                effective_date__lte=date_to,
            )
            .select_related("provider")
            .order_by("-effective_date", "-ingestion_ts")
        )

        data = RateSerializer(rates, many=True).data
        cache.set(cache_key, data, timeout=CACHE_TTL_SECONDS)
        log.info(
            "api.cache_miss",
            extra={
                "endpoint": "history",
                "provider": provider_slug,
                "rate_type": rate_type,
                "count": len(data),
            },
        )
        return data, False

    @staticmethod
    def history_date_window(
        from_param: str | None, to_param: str | None
    ) -> tuple[dt.date, dt.date]:
        """Resolve ?from=&to= into a bounded date window (default trailing 30 days)."""
        date_to = parse_date(to_param) or dt.date.today()
        date_from = parse_date(from_param) or (date_to - dt.timedelta(days=30))
        return date_from, date_to

    @staticmethod
    def browse_queryset(params):
        """Build a filtered, ordered queryset for GET /rates/browse."""
        qs = Rate.objects.select_related("provider").all()

        if rate_type := params.get("rate_type"):
            qs = qs.filter(rate_type=rate_type)
        if provider := params.get("provider"):
            qs = qs.filter(provider__slug=provider)
        if date_from := parse_date(params.get("from")):
            qs = qs.filter(effective_date__gte=date_from)
        if date_to := parse_date(params.get("to")):
            qs = qs.filter(effective_date__lte=date_to)

        return qs.order_by("-effective_date", "-ingestion_ts")

    @staticmethod
    def quarantined_queryset():
        return RawResponse.objects.filter(status=RawResponse.Status.FAILED).order_by(
            "-created_at"
        )

    @staticmethod
    def get_meta() -> dict:
        rate_types = list(
            Rate.objects.values_list("rate_type", flat=True)
            .distinct()
            .order_by("rate_type")
        )
        providers = list(Provider.objects.values("slug", "name").order_by("name"))
        return {"rate_types": rate_types, "providers": providers}
